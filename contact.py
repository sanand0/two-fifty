from google.appengine.ext                 import webapp
import wsgiref.handlers, atom, gdata.contacts, gdata.contacts.service

class AuthPage(webapp.RequestHandler):
    def get(self):
        gd_client = gdata.contacts.service.ContactsService()
        url = gd_client.GenerateAuthSubURL('http://localhost:8080/contact/get', 'http://www.google.com/m8/feeds/', False, True).to_string()
        self.redirect(url)

class GetPage(webapp.RequestHandler):
    def get(self):
        gd_client = gdata.contacts.service.ContactsService()
        gd_client.SetAuthSubToken(self.request.get('token'))
        gd_client.UpgradeToSessionToken()
        query = gdata.contacts.service.ContactsQuery()
        query.max_results = 100
        feed = gd_client.GetContactsFeed(query.ToUri())
        self.response.headers["Content-Type"] = "text/plain"
        for i, entry in enumerate(feed.entry):
            self.response.out.write('\n%s %s' % (i+1, entry.title.text))

application = webapp.WSGIApplication([
        ('/contact/auth', AuthPage),
        ('/contact/get',  GetPage),
    ],
    debug=True)

if __name__ == '__main__':
    wsgiref.handlers.CGIHandler().run(application)
