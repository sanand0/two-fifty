import wsgiref.handlers, urllib, re, datetime, logging, recodata
from BeautifulSoup                        import BeautifulSoup
from google.appengine.ext                 import webapp, db
from google.appengine.api                 import users, urlfetch, memcache
from google.appengine.ext.webapp          import template
from google.appengine.api.urlfetch_errors import *

user            = users.get_current_user()
now             = datetime.datetime.now()
yesterday       = now - datetime.timedelta(1)
page            = 'index2.html'

class Top250(db.Model):
    time = db.DateTimeProperty   (required=True, auto_now_add=True)     # At this time,
    data = db.TextProperty       (required=True)                        # this was the contents of the IMDb Top 250

class Seen(db.Model):
    user = db.UserProperty       (required=True)                        # This user,
    time = db.DateTimeProperty   (required=True, auto_now_add=True)     # at this time,
    url  = db.StringProperty     (required=True)                        # saw this movie

class Count(db.Model):
    user = db.UserProperty       (required=True)                        # Primary key: user
    time = db.DateTimeProperty   (required=True, auto_now_add=True)     # Last modified date
    num  = db.IntegerProperty    (required=True)                        # Number of movies seen, when last counted
    disp = db.StringProperty     ()                                     # Display name

class MoviePage(webapp.RequestHandler):
    # Conventions: person = whose information is shown on the page
    #              user   = who you are logged in as
    def get(self, person=user):
        if person == user: self.show_page(person)
        else: self.show_page(users.User(urllib.unquote(person)))

    def post(self):
        url, disp = self.request.get('movie'), self.request.get('disp')
        if user and url:
            # Toggles the movie watched state for the user
            seen = Seen.all().filter('user = ', user).filter('url = ', url).get()
            if seen:
                seen.delete()
                user_prop(user, change_count=-1)
            else:
                Seen(user=user, time=now, url=url).put()
                user_prop(user, change_count=+1)
            self.response.out.write(url)
        elif user and disp:
            # TODO: disp cannot contain @, /, ...
            if all(ord(c) < 128 for c in disp):                                 # Ensure that disp is pure ascii. Django templates croak otherwise
                user_prop(user, set_disp = disp)                                # Change display name for user
                self.redirect('/')                                              # Go back to user's page
            else: self.response.out.write('Use only letters and numbers')       # Notify error
        else: self.response.out.write('Not logged in, or no URL');

    def show_page(self, person = None):
        if last_download_date() < yesterday: download_250()                     # If we downloaded over a day ago,
        movies = read_250_from_db()                                             # Read from the datastore
        compare_days = 10                                                       # Number of days prior to compare with
        new_movies = extract_new(movies, read_250_from_db(compare_days))        # Extract new movies since compare_days ago
        if person:                                                              # If it's movies for a person,
            person_count = mark_seen_movies(movies, person)                     #   Count the number of movies the person has seen
            person_info  = user_prop(person, set_count = person_count)          #   and save it in the datastore
            person_recos = get_recos(movies)[0:10]
        else: person_info = None
        user_info       = Count.all().filter('user = ', user).get()             # User's count, name, etc.
        can_change      = user==person and user
        top_watchers    = get_top_watchers()
        recent_users    = get_recent_users()
        request         = self.request
        self.response.out.write(template.render(page, dict(locals().items() + globals().items())))

class NamePage(webapp.RequestHandler):
    def get(self, disp):
        person_info = Count.all().filter('disp = ', urllib.unquote(disp)).get()
        if person_info:
            p = MoviePage()
            p.initialize(self.request, self.response)
            p.show_page(person_info.user)

def from_disp_or_email(name):
    name = urllib.unquote(name)
    if name.find('@') > 0: return Count.all().filter('user = ', users.User(name)).get()
    else:                  return Count.all().filter('disp = ', name).get()

class ComparePage(webapp.RequestHandler):
    def get(self, person, other):
        person_info  = from_disp_or_email(person)                               # person can be disp name or email ID (needs @ -- shouldn't be nickname)
        user_info    = Count.all().filter('user = ', user).get()
        if other: other_info = from_disp_or_email(other)
        else: person_info, other_info = user_info, person_info                  # The other is the current user by default
        if person_info and other_info:
            person, other = person_info.user, other_info.user
            if last_download_date() < yesterday: download_250()                 # Download IMDb Top 250 if it's over a day old
            movies = read_250_from_db()                                         # Read from the datastore
            count_person = mark_seen_movies(movies, person, 'person')           # Mark the number of movies person has seen
            count_other  = mark_seen_movies(movies, other , 'other' )           # Mark the number of movies other has seen
            top_watchers = get_top_watchers()
            recent_users = get_recent_users()
            self.response.out.write(template.render(page, dict(locals().items() + globals().items())))

def encode(dict): return '\t'.join(key + ':' + dict[key] for key in dict)
def decode(str): return dict(pair.split(':',1) for pair in str.split('\t'))

def get_top_watchers():
  data = memcache.get('top_watchers')
  if data is not None:
    return data
  else:
    data = Count.all().order('-num').fetch(20)
    memcache.add('top_watchers', data, 3600)
    return data

def get_recent_users():
  data = memcache.get('recent_users')
  if data is not None:
    return data
  else:
    data = Count.all().order('-time').fetch(10)
    memcache.add('recent_users', data, 3600)
    return data

def download_250():
    '''Downloads the top 250 movies on IMDb and saves it in the data store'''
    try:
        movies, result = [], urlfetch.fetch('http://www.imdb.com/chart/top')        # Get the IMDB Top 250
        logging.info('Refreshing IMDb Top 250. Status = ' + str(result.status_code))
        if result.status_code == 200:
            re_scripts = re.compile(r'<script.*?</script', re.I + re.S)             # Remove <script></script> tags: they interfere with BeautifulSoup
            soup = BeautifulSoup(re.sub(re_scripts, '', result.content))
            for movie in soup.findAll('a', href=re.compile(r'^/title/.*')):         # Assumption: only movie URLs (href="/title/...") are the Top 250
                cell = movie.findParent('tr').findAll('td')
                movies.append({
                    'url': (x[1] for x in movie.attrs if x[0] == 'href').next(),    # URL will be used as the unique identifier
                    'title': movie.string,                                          # Only movie name, not the year. Kept HTML encoded.
                    'year': re.search(r'\((\d+).*?\)', str(cell[2].font)).group(1), # Structure: <font><a..>Movie name</a> (2004/I)</font>
                    'rank': cell[0].font.b.string.replace('.', ''),                 # Structure: <font><b>250.</b></font>
                    'rating': cell[1].font.string,                                  # Structure: <font>9.0</font>
                    'votes': cell[3].font.string,                                   # Structure: <font>100,000</font>
                })
            Top250(time=now, data='\n'.join(encode(movie) for movie in movies)).put()
    except:
        pass

def read_250_from_db(n=None):
    q = Top250.all().order('-time')                                                 # Want the most recent
    top = n and q.filter('time < ', now - datetime.timedelta(n)).get() or q.get()   # before n 'days'
    return top and list(decode(line) for line in top.data.split('\n')) or ()        # Decode it and send it back

def last_download_date():
    top = Top250.all().order('-time').get()
    return top and top.time or datetime.datetime(1900, 1, 1)

def mark_seen_movies(movies, user, param='seen'):                                   # Loops through movies, setting param to last seen date (if seen)
    count, seen = 0, {}
    for movie in Seen.all().filter('user = ', user): seen[movie.url] = movie.time   # Get the user's seen movies as a dict
    for movie in movies:
        movie[param] = seen.get(movie['url'], False)                                # Mark the seen movies in the full 250 movie list
        if movie[param]: count += 1                                                 # Count movies in the 250 that the user has seen
    return count                                                                    # Return the seen count

def extract_new(new, old):
    urls = dict.fromkeys((movie['url'] for movie in old),1)
    return tuple(movie for movie in new if not movie['url'] in urls)

def get_recos(movies, param='seen'):
    index = dict((v,i) for i,v in enumerate(recodata.movies))
    count, seen_movies, all_movies = {}, {}, {}
    for movie in movies:
        url = movie['url']
        all_movies[url] = movie
        if movie[param] and url in index:
            seen_movies[url] = 1
            for j, total in enumerate(recodata.similar[index[url]]):
                m = recodata.movies[j]
                count[m] = count.get(m, 0) + total
    return tuple(all_movies[url] for url in sorted(count.keys(), key=count.__getitem__, reverse=True) if not url in seen_movies and url in all_movies)

# TODO: This is a BAD function. Refactor.
def user_prop(person, set_count = None, change_count = None, set_disp = None):
    # Get the person info, creating it only if the person is the user
    person_info = Count.all().filter('user = ', person).get()
    if not person_info and user == person and (set_count or change_count or set_disp):
        person_info = Count(user=person, time=now, num=0)

    if person_info:
        # Get the new "seen count" into num, and update it if it's changed (anyone can update that)
        num, changed = person_info.num, 0
        if set_count    is not None:  num  = int(set_count)
        if change_count is not None:  num += int(change_count)
        if (set_count or change_count) and person_info.num != num: person_info.num, changed = num, 1

        # Only the user can change the display name
        if user==person and set_disp and person_info.disp != set_disp: person_info.disp, changed = set_disp, 1

        # Update the time only if something's changed
        if changed:
            if user == person: person_info.time = now
            person_info.put()

    return person_info

class LoginPage(webapp.RequestHandler):
    def get(self): self.redirect(users.create_login_url('/'))

class LogoutPage(webapp.RequestHandler):
    def get(self): self.redirect(users.create_logout_url('/'))

class DataPage(webapp.RequestHandler):
    def get(self, person, data):
        self.response.headers["Content-Type"] = "application/javascript"
        callback = self.request.get('callback')
        if data == 'users':
            if user and users.is_current_user_admin():
                userlist = Count.all().fetch(1000)
                self.response.out.write(template.render('users.txt', locals()))
        else:
            person      = users.User(urllib.unquote(person))
            person_info = Count.all().filter('user = ', person).get()
            if person_info:
                person_disp = person_info.disp or person.nickname()
                if data == 'count':
                    self.response.out.write(template.render('count.txt', locals()))
                elif data == 'seen':
                    movies = read_250_from_db()
                    count  = mark_seen_movies(movies, person)
                    self.response.out.write(template.render('seen.txt', locals()))

application = webapp.WSGIApplication([
        ('/',                       MoviePage),
        ('/user/(.+)',              MoviePage),
        ('/name/(.+)',              NamePage),
        ('/data/(.+)/(.+)',         DataPage),
        ('/compare/([^/]+)/?(.+)?', ComparePage),
        ('/login',                  LoginPage),
        ('/logout',                 LogoutPage),
    ],
    debug=True)
wsgiref.handlers.CGIHandler().run(application)
