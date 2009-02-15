function twofifty_seen(data) {
    var seen = [], html = [];
    for (var i=0, m; m=data.movies[i]; i++) { if (m.seen) { seen.push(m); } }
    seen.sort(function(a,b) { return a.seen < b.seen ? 1 : 0; });
    for (var i=0, m; (i<5) && (m=seen[i]); i++) {
        html.push('<a href="http://www.imdb.com' + m.url + '">' + m.title + '</a>');
    }
    document.write(
        '<div style="width:250px">' +
            '<div style="font:12px sans-serif">Last 5 movies seen on the <a href="http://250.s-anand.net/user/' + data.user + '">IMDb Top 250</a><br/>' +
            html.join('<br/>') +
        '</div></div>'
    );
}