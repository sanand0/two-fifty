import wsgiref.handlers, recodata, datetime, urllib
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

class RecoPage(webapp.RequestHandler):
    def get(self, person=user):
        if isinstance(person, str): person = users.User(urllib.unquote_plus(person))
        if person:
            # Get their movies
            count, seen_movies = {}, {}
            index = dict((v,i) for i,v in enumerate(recodata.movies))
            for seen in Seen.all().filter('user = ', person):
                if seen.url in index:
                    seen_movies[seen.url] = 1
                    for j, total in enumerate(recodata.similar[index[seen.url]]):
                        movie = recodata.movies[j]
                        count[movie] = count.get(movie, 0) + total
            recos = tuple(movie for movie in sorted(count.keys(), key=count.__getitem__, reverse=True) if not movie in seen_movies)
            self.response.out.write(repr(recos[0:10]))


application = webapp.WSGIApplication([
        ('/reco/(.*)',              RecoPage),
    ],
    debug=True)
wsgiref.handlers.CGIHandler().run(application)

