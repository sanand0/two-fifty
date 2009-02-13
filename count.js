function twofifty_count(data) {
    document.write(
        '<div style="text-align:center;width:100px">' +
            '<div style="font:50px sans-serif"><a style="font:50px Impact, sans-serif; text-decoration:none" href="http://250.s-anand.net/user/' + data.user + '">' + data.count + '</a></div>' +
            '<div style="font:11px sans-serif">movies seen on<br/>the <a href="http://250.s-anand.net/user/' + data.user + '">IMDb Top 250</a></div>' +
        '</div>'
    );
}