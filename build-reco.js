$(function() {
    // Define a standard scraping function
    // Ensure that the url and xpath parameters cannot contain double-quotes (")
    var scrape = function (url, xpath, fn) {
        $.getJSON('http://query.yahooapis.com/v1/public/yql?callback=?', {
            q: 'select * from html where url="' + url + '" and xpath="' + xpath + '"',
            format: 'json'
        }, fn);
    };

    // Get the IMDb Top 250
    scrape('http://www.imdb.com/chart/top', '//tr//tr//tr//td[3]//a', function(data) {
        var movies = data.query.results.a,                                                  // Get the movie links
            movie = movies[Math.round(Math.random() * movies.length)];                      // Pick a random movie
        scrape('http://www.imdb.com' + movie.href + 'recommendations', "//td/font//a[contains(@href,'/title/')]", function(data) {
            $.post('/build-reco', {                                                         // Push them to the server
                url: movie.href,
                title: movie.content.replace(/\s+/g, ' '),
                reco: $.map(data.query.results.a, function(m) { return m.href + "\t" + m.content.replace(/\s+/g, ' '); }).join("\t")
            });
        });
    });
});