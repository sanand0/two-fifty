import wsgiref.handlers, urllib, re, datetime, logging
from BeautifulSoup                        import BeautifulSoup
from google.appengine.ext                 import webapp, db
from google.appengine.api                 import users, urlfetch
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
    num  = db.IntegerProperty    (required=True)
    disp = db.StringProperty     ()

class MoviePage(webapp.RequestHandler):
    # Conventions: person = whose information is shown on the page
    #              user   = who you are logged in as
    def get(self, person=user):
        if person == user: self.show_page(person)
        else: self.show_page(users.User(urllib.unquote_plus(person)))

    def post(self):
        url, disp = self.request.get('movie'), self.request.get('disp')
        if user and url:
            # Toggles the movie watched state for the user
            seen = Seen.all().filter('user = ', user).filter('url = ', url).get()
            if seen:
                seen.delete()
                set_user_info(user, change_count=-1)
            else:
                Seen(user=user, time=now, url=url).put()
                set_user_info(user, change_count=+1)
            self.response.out.write(url)
        elif user and disp:
            set_user_info(user, disp = disp)                                    # Change display name for user
            self.redirect('/')                                                  # Go back to user's page
        else: self.response.out.write('Not logged in, or no URL');

    def show_page(self, person = None):
        if last_download_date() < now - a_day: download_250()                   # Download IMDb Top 250 if it's over a day old
        movies = read_250_from_db()                                             # Read from the datastore
        if person:                                                              # If it's movies for a person,
            count  = mark_seen_movies(movies, person)                           #   Count the number of movies the person has seen
            person_info = set_user_info(person, set_count = count)              #   and save it in the datastore
        else: count, person_info = 0, None
        user_info       = Count.all().filter('user = ', user).get()                     # User's count, name, etc.
        person_disp     = person_info and (person_info.disp or person.nickname()) or ''
        user_disp       = user_info and (user_info.disp or user.nickname()) or ''
        logged_in       = user and 1 or 0
        can_change      = user==person and user
        top_watchers    = Count.all().order('-num').fetch(20)
        recent_users    = Count.all().order('-time').fetch(10)
        self.response.out.write(template.render('index.html', locals()))

def encode(dict): return '\t'.join(key + ':' + dict[key] for key in dict)
def decode(str): return dict(pair.split(':',1) for pair in str.split('\t'))

def download_250():
    '''Downloads the top 250 movies on IMDb and saves it in the data store'''
    try:
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
    except:
        pass

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

def set_user_info(user, set_count = None, change_count = None, disp = None):
    user_info = Count.all().filter('user = ', user).get() or Count(user=user, time=now, num=0)
    if set_count    is not None:  user_info.num   = int(set_count)
    if change_count is not None:  user_info.num  += int(change_count)
    if disp         is not None:  user_info.disp  = disp
    user_info.time = now
    user_info.put()
    return user_info

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
