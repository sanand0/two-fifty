from google.appengine.dist import use_library
use_library('django', '1.2')

import wsgiref.handlers, urllib, re, datetime, logging, recodata, operator
from BeautifulSoup                        import BeautifulSoup
from google.appengine.ext                 import webapp, db, ereporter
from google.appengine.api                 import users, urlfetch, memcache
from google.appengine.ext.webapp          import template
from google.appengine.api.urlfetch_errors import *

try:    user = users.get_current_user()
except: user = None
now          = datetime.datetime.now()
yesterday    = now - datetime.timedelta(1)
page         = 'index.html'

# http://blog.notdot.net/2010/03/Using-the-ereporter-module-for-easy-error-reporting-in-App-Engine
ereporter.register_logger()

def memcache_setdefault(key, value, time):
    memcache.set(key, value, time)
    return value

class Top250(db.Model):
    time = db.DateTimeProperty   (required=True, auto_now_add=True)     # At this time,
    data = db.TextProperty       (required=True)                        # this was the contents of the IMDb Top 250

class Seen(db.Model):
    user = db.UserProperty       (required=True)                        # This user,
    time = db.DateTimeProperty   (required=True, auto_now_add=True)     # at this time,
    url  = db.StringProperty     (required=True)                        # saw this movie

class SeenTitle(db.Model):
    user  = db.UserProperty       (required=True)                       # This user,
    time  = db.DateTimeProperty   (required=True, auto_now_add=True)    # at this time,
    title = db.StringProperty     (required=True)                       # saw this movie
    year  = db.StringProperty     (required=True)                       # dated...

class Count(db.Model):                                                  # (This is really the User master)
    user    = db.UserProperty      (required=True)                      # Primary key: user
    time    = db.DateTimeProperty  (required=True, auto_now_add=True)   # Last date a movie was marked by user
    num     = db.IntegerProperty   (required=True)                      # Number of movies seen, when last counted
    login   = db.DateTimeProperty  ()                                   # Last logged in date
    email   = db.DateTimeProperty  ()                                   # Date the user was last sent an email
    twitter = db.StringProperty    ()                                   # Twitter user ID
    disp    = db.StringProperty    ()                                   # Display name
    rel     = db.TextProperty      ()                                   # TSV of relation => user
    donated = db.IntegerProperty   ()                                   # contributed this many dollars

class Activity(db.Model):                                               # Daily feed of user activity.
    time = db.DateTimeProperty   (required=True, auto_now_add=True)     # Last modified date
    data = db.TextProperty       ()                                     # TSV of relation => user

class MoviePage(webapp.RequestHandler):
    # Conventions: person = whose information is shown on the page
    #              user   = who you are logged in as
    def get(self, person=user):
        if person == user: self.show_page(person)
        else: self.show_page(users.User(urllib.unquote(person)))

    def post(self):
        movie, disp = (self.request.get(x) for x in ('movie', 'disp'))
        title, year = (self.request.get(x) for x in ('title', 'year'))
        if not user:                                                            # Must be logged in to make any changes
            self.response.out.write('Not logged in')
            return

        if movie:                                                               # Toggle the movie watched state for the user
            seen = Seen.all().filter('user = ', user).filter('url = ', movie).get()
            if seen:
                seen.delete()
                user_prop(user, change_count=-1)
            else:
                Seen(user=user, time=now, url=movie).put()
                user_prop(user, change_count=+1)
            self.response.out.write(movie)

        elif title and year:                                                    # Toggle a seen movie by title and year
            seen = SeenTitle.all().filter('user = ', user)
            seen = seen.filter('title = ', title)
            seen = seen.filter('year = ', year).get()
            if seen:
                seen.delete()
            else:
                SeenTitle(user=user, time=now, title=title, year=year).put()
            self.response.out.write(title)

        elif disp:                                                              # Change the display name. TODO: disp cannot contain @, /, ...
            if all(ord(c) < 128 for c in disp):                                 # Ensure that disp is pure ascii. Django templates croak otherwise
                user_prop(user, set_disp = disp)                                # Change display name for user
                self.redirect('/')                                              # Go back to user's page
            else: self.response.out.write('Use only letters and numbers')       # Notify error

    def show_page(self, person = None):
        movies          = read_250_from_db()                                    # Read from the datastore
        compare_days    = 5                                                     # Number of days prior to compare with. TODO: Change this to days since last login
        new_movies      = extract_new(movies, read_250_from_db(compare_days))   # Extract new movies since compare_days ago
        user_info       = Count.all().filter('user = ', user).get()             # User's count, name, etc.
        user_rel, user_followers = None, None
        if user_info:
            user_rel    = rel2dict(user_info.rel)
            if user==person: user_followers = get_follower_info(user_rel)
        if person:                                                              # If it's movies for a person,
            person_count = mark_seen_movies(movies, person)                     #   Count the number of movies the person has seen
            person_info  = user_prop(person, set_count = person_count)          #   and save it in the datastore
            person_info  = mark_rel([person_info], user_rel)[0]                 # Mark the rel tags
            person_recos = get_recos(movies)[0:10]
        else: person_info = None
        just_logged_in  = False
        if self.request.get('login') and user_info:                             # If the user's just logged in, he'll be redirected to /?login=1
            user_info.login = now                                               # So set the last logged-in date for the user
            just_logged_in  = True                                              # Google analytics variable
            user_info.put()
        can_change      = user==person and user
        top_watchers    = mark_rel(get_top_watchers(), user_rel)
        recent_users    = mark_rel(get_recent_users(), user_rel)
        request         = self.request
        self.response.out.write(template.render(page, dict(locals().items() + globals().items())))

class NamePage(webapp.RequestHandler):
    def get(self, disp):
        person_info = Count.all().filter('disp = ', urllib.unquote(disp)).get() # TODO: memcache
        if person_info:
            p = MoviePage()
            p.initialize(self.request, self.response)
            p.show_page(person_info.user)

def rel2dict(s):
    rel = {}
    for line in (s and s.split('\n') or []):
        fields = line.split('\t')
        rel.setdefault(fields[0], {})[fields[1]] = fields[2]
    return rel

def dict2rel(rel):
    s = []
    for tag in rel:
        for key in rel[tag]:
            s.append(tag + '\t' + key + '\t' + rel[tag][key])
    return '\n'.join(s)

def get_follower_info(rel):
    if 'follower' not in rel: return []
    follower_info = []
    for other in rel['follower']:
        follower_info.append(Count.all().filter('user = ', users.User(other)).get())
    follower_info.sort(key=operator.attrgetter('num'))
    follower_info.reverse()
    return follower_info

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
            movies = read_250_from_db()                                         # Read from the datastore
            count_person = mark_seen_movies(movies, person, 'person')           # Mark the number of movies person has seen
            count_other  = mark_seen_movies(movies, other , 'other' )           # Mark the number of movies other has seen
            top_watchers = get_top_watchers()
            recent_users = get_recent_users()
            self.response.out.write(template.render(page, dict(locals().items() + globals().items())))

get_top_watchers = lambda: memcache.get('top_watchers') or memcache_setdefault('top_watchers', Count.all().order('-num' ).fetch(20), 3600)
get_recent_users = lambda: memcache.get('recent_users') or memcache_setdefault('recent_users', Count.all().order('-time').fetch(10), 3600)

def mark_rel(users, rel):
    if not rel: return users
    for user in users:
        for tag in rel:
            if user:
                other = user.user.email()
                if other in rel[tag]:
                    user.__setattr__(tag, rel[tag][other])
    return users

def download_250():
    '''Downloads the top 250 movies on IMDb and saves it in the data store'''
    movies, result = [], urlfetch.fetch('http://www.imdb.com/chart/top')        # Get the IMDB Top 250
    logging.info('Refreshing IMDb Top 250. Status = ' + str(result.status_code))
    if result.status_code == 200:
        soup = BeautifulSoup(result.content)
        for movie in soup.findAll('a', href=re.compile(r'^/title/.*')):         # Assumption: only movie URLs (href="/title/...") are the Top 250
            cell = movie.findParent('tr').findAll('td')
            movies.append({
                'url': (x[1] for x in movie.attrs if x[0] == 'href').next(),    # URL will be used as the unique identifier
                'title': movie.string,                                          # Only movie name, not the year. Kept HTML encoded.
                'year': re.search(r'\((\d\d\d\d).*?\)', str(cell[2].font)).group(1), # Structure: <font><a..>Movie name</a> (2004/I)</font>
                'rank': cell[0].font.b.string.replace('.', ''),                 # Structure: <font><b>250.</b></font>
                'rating': cell[1].font.string,                                  # Structure: <font>9.0</font>
                'votes': cell[3].font.string,                                   # Structure: <font>100,000</font>
            })
        def encode(dict): return '\t'.join(key + ':' + dict[key] for key in dict)
        Top250(time=now, data='\n'.join(encode(movie) for movie in movies)).put()

def read_250_from_db(n=0):
    date = now - datetime.timedelta(n)
    key = 'read_250_from_db' + date.strftime('%Y-%m-%d')
    data = memcache.get(key)
    if not data:
        def decode(str): return dict(pair.split(':',1) for pair in str.split('\t'))
        q = Top250.all().order('-time')                                                 # Want the most recent
        top = n and q.filter('time < ', date).get() or q.get()                          # before n 'days'
        data = top and list(decode(line) for line in top.data.split('\n')) or ()        # Decode it and send it back
    return memcache_setdefault(key, data, 12 * 3600)

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
    person_info = Count.all().filter('user = ', person).get()       # TODO: memcache
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

        if changed:                                     # Update the time only if something's changed
            if user == person: person_info.time = now
            person_info.put()

    return person_info


def _html_convert(c): return

class DataPage(webapp.RequestHandler):
    def get(self, person, data):
        self.response.headers["Content-Type"] = "application/javascript"
        callback    = self.request.get('callback')
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
            elif data == 'seentitle':
                movies = read_250_from_db()
                count  = mark_seen_movies(movies, person)
                titles = SeenTitle.all().filter('user = ', person).fetch(1000)
                self.response.out.write(template.render('seen.txt', locals()))

class FollowPage(webapp.RequestHandler):
    def get(self, request, other):
        if user:
            if request == 'follow': tag, value = 'follower', '1'
            else:                   tag, value = 'follower', None
            rev = 'is-' + tag + '-of'
            other = urllib.unquote(other)
            user_info   = Count.all().filter('user = ', user).get()
            other_info  = Count.all().filter('user = ', users.User(other)).get()
            if other_info:
                user_rel        = rel2dict(user_info.rel)
                other_rel       = rel2dict(other_info.rel)
                if value:       user_rel.setdefault(tag, {})[other] = other_rel.setdefault(rev, {})[user.email()] = value
                else:           del user_rel[tag][other],  other_rel[rev][user.email()]
                user_info.rel   = dict2rel(user_rel)
                other_info.rel  = dict2rel(other_rel)
                user_info.put()
                other_info.put()
        self.redirect('/')

class RefreshPage(webapp.RequestHandler):
    def get(self): download_250()

class FeedRefreshPage(webapp.RequestHandler):
    def get(self):
        title = dict(((movie['url'], movie['title']) for movie in read_250_from_db()))
        count, activity = 0, {}
        for seen in Seen.all().filter('time >=', yesterday):
            activity.setdefault(seen.user, []).append({'title':title.get(seen.url, 'some movie'), 'url':seen.url})
            count += 1
        activity = activity.items()
        rss = template.render('feed.xml', { 'updated': now, 'activity': activity, 'count': count, 'people': len(activity) })
        Activity(time=now, data=rss).put()

class FeedPage(webapp.RequestHandler):
    def get(self):
        self.response.headers["Content-Type"] = "text/xml"
        self.response.out.write(Activity.all().order('-time').get().data)

class Feed250Page(webapp.RequestHandler):
    def get(self):
        self.response.headers["Content-Type"] = "text/xml"
        self.response.out.write(template.render('feed250.xml', { 'movies': read_250_from_db(), 'today': now.replace(hour=0, minute=0, second=0) }))

class LoginPage(webapp.RequestHandler):
    def get(self): self.redirect(users.create_login_url('/?login=1'))

class LogoutPage(webapp.RequestHandler):
    def get(self): self.redirect(users.create_logout_url('/'))

class ContributePage(webapp.RequestHandler):
    '''
    Contribution is an experiment. Not a way of making money.
    To avoid distraction, I will turn it off once I have 30 payments
    (30 datapoints required for reasonable statistical significance)
    Check whether $1 or $2 makes a difference.
    Check whether PayPal symbol makes a difference.

    Launched: 9-Sep-2010
    Estimate: 30 people/day, 1/500 pay, 4 pay in month 1, 10 pay in month 4.
    Shutdown: 6-Oct-2010. 12 people donated $14
    Turned off because I made some stupid mistake with Google Website Optimizer
    and it wasn't tracking anything anyway.
    '''
    def get(self, amount):
        if user:
            # Log info about user's contribution
            amount = int(amount)
            user_info  = Count.all().filter('user = ', user).get()
            if not user_info.donated: user_info.donated = amount
            else: user_info.donated += amount
            user_info.put()

            # Redirect to PayPal
            if amount == 1:
                self.redirect('https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=L2UFCKYTW9A8E')
            else:
                self.redirect('https://www.paypal.com/cgi-bin/webscr?cmd=_s-xclick&hosted_button_id=2KXDDHHKU8NBL')
        else:
            self.redirect(users.create_login_url('/?login=1'))

class VisualPage(webapp.RequestHandler):
    '''
    An experiment in visualising the top movies
    '''
    def get(self, person=user):
        if not person: person = user
        else: person = users.User(urllib.unquote(person))
        if not person:
            return self.redirect(users.create_login_url('/visual'))
        else:
            other_page = person != user
            self.response.out.write(template.render('visual.html', locals()))

application = webapp.WSGIApplication([
        ('/',                       MoviePage),
        ('/user/(.+)',              MoviePage),
        ('/name/(.+)',              NamePage),
        ('/visual/?(.+)?',          VisualPage),
        ('/data/(.+)/(.+)',         DataPage),
        ('/compare/([^/]+)/?(.+)?', ComparePage),
        ('/login',                  LoginPage),
        ('/logout',                 LogoutPage),
        ('/(follow|unfollow)/(.+)', FollowPage),
        ('/refresh',                RefreshPage),
        ('/feed/refresh',           FeedRefreshPage),
        ('/feed',                   FeedPage),
        ('/feed250',                Feed250Page),
        ('/contribute/(\d+)',       ContributePage),
    ],
    debug=False)

if __name__ == '__main__':
    wsgiref.handlers.CGIHandler().run(application)
