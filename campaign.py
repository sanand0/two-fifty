'''
Emails people who're not active: (not logged in for 2 months) or (haven't marked a movie for 6 months && have unseen movies)
'''

import wsgiref.handlers, urllib, logging
from datetime                       import timedelta
from twofifty                       import now, Count, extract_new, read_250_from_db, mark_seen_movies, user_prop
from google.appengine.ext           import webapp, db
from google.appengine.api           import mail, users
from google.appengine.ext.webapp    import template

MAX_MAILS_PER_REQUEST = 3

class MailPage(webapp.RequestHandler):
    def get(self, user=None):
        self.response.headers["Content-Type"] = "text/plain"
        if user: to_list = [Count.all().filter('user = ', users.User(urllib.unquote(user))).get()]
        else:
            not_marked_recently  = Count.all().filter('time < ' , now - timedelta(days=150)).fetch(100)
            not_visited_recently = Count.all().filter('login < ', now - timedelta(days=60 )).fetch(100)
            to_list = [x for x in not_marked_recently + not_visited_recently if x.email is None][:MAX_MAILS_PER_REQUEST]

        for person_info in to_list:
            last_visited = person_info.login or person_info.time
            movies       = read_250_from_db()
            compare_days = (now - last_visited).days
            new_movies   = extract_new(movies, read_250_from_db(compare_days))      # Extract new movies since compare_days ago

            if new_movies:
                user_count  = mark_seen_movies(movies, user)                        # Count the number of movies the person has seen
                person_info = user_prop(person_info.user, set_count = user_count)   # and save it in the datastore
                if person_info:
                    vars = dict(locals().items() + globals().items())
                    mail.send_mail('250@s-anand.net', person_info.user.email(), 'New movies on the IMDb Top 250', template.render('campaign.txt', vars), html=template.render('campaign.html', vars))
                    logging.info('Sent campaign email to ' + person_info.user.email())
                    self.response.out.write(person_info.user.email() + '\n')
                    person_info.email = now
                    person_info.put()

application = webapp.WSGIApplication([
        ('/mail/(.+)',  MailPage),
        ('/mail',       MailPage),
    ],
    debug=True)

if __name__ == '__main__':
    wsgiref.handlers.CGIHandler().run(application)
