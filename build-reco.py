import wsgiref.handlers, logging
from google.appengine.ext                 import webapp, db

class Reco(db.Model):
    time    = db.DateTimeProperty   (required=True, auto_now_add=True)     # At this time,
    url     = db.StringProperty     (required=True)                        # this movie
    title   = db.StringProperty     (required=True)
    reco    = db.TextProperty       (required=True)                        # has these recommendations

class BuildReco(webapp.RequestHandler):
    def post(self):
        url = self.request.get('url')                   # Get POST data
        if not Reco.all().filter('url = ', url).get():  # If there's no recommendation
            Reco(url=url,                               # Create a recommendation
                 title=self.request.get('title'),
                 reco=self.request.get('reco')
            ).put()
            self.response.out.write('Added')
        else:                                           # If not, ignore
            self.response.out.write('Already exists')

application = webapp.WSGIApplication([
        ('/build-reco',             BuildReco),
    ],
    debug=True)
wsgiref.handlers.CGIHandler().run(application)
