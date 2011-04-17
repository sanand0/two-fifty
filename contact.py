from google.appengine.dist import use_library
use_library('django', '1.2')

from google.appengine.ext           import webapp, db
from google.appengine.api           import users, memcache
from google.appengine.api.labs      import taskqueue
from google.appengine.ext.webapp    import template
from twofifty                       import Count, user
import wsgiref.handlers, atom, gdata.contacts, gdata.contacts.service, logging, wsgiref.util, pickle

class Contacts(db.Model):           # Each row is a group of contacts, which together is exhaustive
    users = db.BlobProperty()
    time  = db.DateTimeProperty(required=True, auto_now=True)

class AuthContactsPage(webapp.RequestHandler):
    def get(self):
        gd_client = gdata.contacts.service.ContactsService()
        root = wsgiref.util.application_uri(self.request.environ)
        self.redirect(gd_client.GenerateAuthSubURL(root + 'contact/get', 'http://www.google.com/m8/feeds/', False, True).to_string())

class GenerateContactsPage(webapp.RequestHandler):
    def get(self):
        CHUNK = 500
        users = []
        for row in Contacts.all().fetch(1000): users += pickle.loads(row.users)
        if not users: new = Count.all().order('__key__').fetch(CHUNK)
        else:         new = Count.all().filter('__key__ > ', users[-1].key()).order('__key__').fetch(CHUNK)
        if new:
            users += new
            contacts = Contacts()
            contacts.users = pickle.dumps(users)
            contacts.put()
            if len(new) >= CHUNK:
                taskqueue.add(url='/contact/generate', method='GET')

        # users = memcache.get('all_users') or []
        # logging.info('%d users in cache. ' % len(users))
        # if not users:   new = Count.all().order('__key__').fetch(1000)
        # else:           new = Count.all().order('__key__').filter('__key__ > ', users[-1].key()).fetch(1000)
        # if new:
        #     users += new
        #     memcache.set('all_users', users, 10 * 86400)
        #     logging.info('%d added to cache.' % len(new))
        #     if len(new) >= 1000:
        #         taskqueue.add(url='/contact/generate')
        #         logging.info('Task to add more users scheduled.')


class GetContactsPage(webapp.RequestHandler):
    def get(self):
        userlist = memcache.get('all_users') or []
        emails = dict(((user.user.email(), 1) for user in userlist))

        gd_client = gdata.contacts.service.ContactsService()
        gd_client.SetAuthSubToken(self.request.get('token'))
        gd_client.UpgradeToSessionToken()
        query = gdata.contacts.service.ContactsQuery()
        query.max_results = 500
        feed = gd_client.GetContactsFeed(query.ToUri())
        self.response.headers['Content-Type'] = 'text/plain'
        for entry in feed.entry:
            for email in entry.email:
                self.response.out.write('%s - %s\n' % (email.address in emails and 'Y' or 'N', email.address))

class AllContactsPage(webapp.RequestHandler):
    def get(self):
        self.response.headers['Content-Type'] = 'text/plain'
        userlist = memcache.get('all_users') or []
        if userlist: self.response.out.write(template.render('users.txt', locals()))
        else:        self.response.out.write('No user list')

application = webapp.WSGIApplication([
        ('/contact/auth',     AuthContactsPage),
        ('/contact/get',      GetContactsPage),
        ('/contact/all',      AllContactsPage),         # Shows all the contacts
        ('/contact/generate', GenerateContactsPage),    # Generates a list of contacts and stores it on the database
    ],
    debug=True)

if __name__ == '__main__':
    wsgiref.handlers.CGIHandler().run(application)
