import wsgiref.handlers, urllib, re, datetime, logging
from BeautifulSoup                        import BeautifulSoup
from google.appengine.ext                 import webapp
from google.appengine.ext                 import db
from google.appengine.api                 import users
from google.appengine.api                 import urlfetch
from google.appengine.ext.webapp          import template
from google.appengine.api.urlfetch_errors import *

user   = users.get_current_user()
now    = datetime.datetime.now()
a_day  = datetime.timedelta(1)

class Top250(db.Model):
    time = db.DateTimeProperty   (required=True, auto_now_add=True)
    data = db.TextProperty       (required=True)

class Seen(db.Model):
    user = db.UserProperty       (required=True)
    time = db.DateTimeProperty   (required=True, auto_now_add=True)
    url  = db.StringProperty     (required=True)

class Count(db.Model):
    user = db.UserProperty       (required=True)
    time = db.DateTimeProperty   (required=True, auto_now_add=True)
    num = db.IntegerProperty     (required=True)

class MoviePage(webapp.RequestHandler):
    def get(self, person=user):
        if person == user: self.show_page(person)
        else: self.show_page(users.User(urllib.unquote_plus(person)))

    def post(self):
        '''Toggles the movie watched state for the user'''
        url = self.request.get('movie')
        if user and url:
            seen = Seen.all().filter('user = ', user).filter('url = ', url).get()
            if seen:
                seen.delete()
                set_count(user, -1, add=True)
            else:
                Seen(user=user, time=now, url=url).put()
                set_count(user, +1, add=True)
            self.response.out.write(url)
        else: self.response.out.write('Not logged in, or no URL');

    def show_page(self, person = None):
        if last_download_date() < now - a_day: download_250()                   # Download IMDb Top 250 if it's over a day old
        movies = read_250_from_db()                                             # Read from the datastore
        if person:                                                              # If it's movies for a person,
            seen_count = mark_seen_movies(movies, person)                       #   Count the number of movies the person has seen
            set_count(person, seen_count)                                       #   and save it in the datastore
        else: seen_count = 0
        self.response.out.write(template.render('index.html', dict(             # Display the page
            movies      = movies,
            user        = person,
            logged_in   = user,
            can_change  = user==person and user,
            count       = seen_count,
            stats       = Count.all().order('-num').fetch(10)
        )))

def encode(dict): return '\t'.join(key + ':' + dict[key] for key in dict)
def decode(str): return dict(pair.split(':',1) for pair in str.split('\t'))

def download_250():
    '''Downloads the top 250 movies on IMDb and saves it in the data store'''
    movies = []
    result = urlfetch.fetch('http://www.imdb.com/chart/top')                    # Get the IMDB Top 250
    if result.status_code == 200:
        re_scripts = re.compile(r'<script.*?</script', re.I + re.S)             # Remove <script></script> tags: they interfere with BeautifulSoup
        soup = BeautifulSoup(re.sub(re_scripts, '', result.content))
        for movie in soup.findAll('a', href=re.compile(r'^/title/.*')):         # Assumption: only movie URLs (href="/title/...") are the Top 250
            cell = movie.findParent('tr').findAll('td')
            movies.append({
                'url': (x[1] for x in movie.attrs if x[0] == 'href').next(),    # URL will be used as the unique identifier
                'title': movie.string,                                          # Only movie name, not the year. Kept HTML encoded.
                'year': re.search(r'\((.*)\)', str(cell[2].font)).group(1),     # Structure: <font><a..>Movie name</a> (2004/I)</font>
                'rank': cell[0].font.b.string.replace('.', ''),                 # Structure: <font><b>250.</b></font>
                'rating': cell[1].font.string,                                  # Structure: <font>9.0</font>
                'votes': cell[3].font.string,                                   # Structure: <font>100,000</font>
            })
        data = '\n'.join(encode(movie) for movie in movies)
        Top250(time=now, data=data).put()
    logging.info('Refreshing IMDb Top 250. Status = ' + str(result.status_code))

def read_250_from_db():
    top = Top250.all().order('-time').get()
    return top and list(decode(line) for line in top.data.split('\n')) or ()

def last_download_date():
    top = Top250.all().order('-time').get()
    return top and top.time or datetime.datetime(1900, 1, 1)

def mark_seen_movies(movies, user):
    count, seen = 0, {}
    for movie in Seen.all().filter('user = ', user):
        seen[movie.url] = True
        count = count + 1
    for movie in movies: movie['seen'] = seen.get(movie['url'], False)
    return count

def set_count(user, num, add = False):
    count = Count.all().filter('user = ', user).get()
    if count:
        if add: count.num = count.num + int(num)
        else:   count.num = int(num)
        count.time = now
        count.put()
    else: Count(user=user, time=now, num=num).put()

class LoginPage(webapp.RequestHandler):
    def get(self): self.redirect(users.create_login_url('/'))

class LogoutPage(webapp.RequestHandler):
    def get(self): self.redirect(users.create_logout_url('/'))

application = webapp.WSGIApplication([
        ('/',                   MoviePage),
        ('/user/(.+)',          MoviePage),
        ('/login',              LoginPage),
        ('/logout',             LogoutPage),
    ],
    debug=True)
wsgiref.handlers.CGIHandler().run(application)
