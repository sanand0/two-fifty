'''
Emails people who're not active: (not logged in for 2 months) or (haven't marked a movie for 6 months && have unseen movies)
'''

import wsgiref.handlers, urllib
from datetime                       import timedelta
from twofifty                       import now, Count, extract_new, read_250_from_db
from google.appengine.ext           import webapp, db
from google.appengine.api           import mail, users
from google.appengine.ext.webapp    import template

MAX_MAILS_PER_REQUEST = 1

class MailPage(webapp.RequestHandler):
    def get(self, user=None):
        if user: to_list = [Count.all().filter('user = ', users.User(urllib.unquote(user))).get()]
        else:
            not_marked_recently  = Count.all().filter('time < ' , now - timedelta(days=180)).fetch(100)
            not_visited_recently = Count.all().filter('login < ', now - timedelta(days=60 )).fetch(100)
            to_list = [x for x in not_marked_recently + not_visited_recently if x.email is None][:MAX_MAILS_PER_REQUEST]

        for user_info in to_list:
            last_visited = user_info.login or user_info.time
            compare_days = (now - last_visited).days
            new_movies = extract_new(read_250_from_db(), read_250_from_db(compare_days))    # Extract new movies since compare_days ago

            if new_movies:
                self.response.headers["Content-Type"] = "text/plain"
                self.response.out.write(template.render('campaign.txt', dict(locals().items() + globals().items())))
                # mail.send_mail('250@s-anand.net', [user_info.user.email(), '250@s-anand.net'], 'New movies on the IMDb Top 250', template.render('campaign.txt', dict(locals().items() + globals().items())))
                # user_info.email = now
                # user_info.put()

application = webapp.WSGIApplication([
        ('/mail/(.+)',  MailPage),
        ('/mail',       MailPage),
    ],
    debug=True)

if __name__ == '__main__':
    wsgiref.handlers.CGIHandler().run(application)
