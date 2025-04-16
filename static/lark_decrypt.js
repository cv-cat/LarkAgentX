function T(e, t) {
    var n = (65535 & e) + (65535 & t);
    return (e >> 16) + (t >> 16) + (n >> 16) << 16 | 65535 & n
}
function f(e, t, n, i, r, a) {
    return T((o = T(T(t, e), T(i, a))) << (s = r) | o >>> 32 - s, n);
    var o, s
}
function h(e, t, n, i, r, a, o) {
    return f(t & n | ~t & i, e, t, r, a, o)
}
function y(e, t, n, i, r, a, o) {
    return f(t & i | n & ~i, e, t, r, a, o)
}
function S(e, t, n, i, r, a, o) {
    return f(t ^ n ^ i, e, t, r, a, o)
}
function A(e, t, n, i, r, a, o) {
    return f(n ^ (t | ~i), e, t, r, a, o)
}
function g(e, t) {
    var n, i, r, a, o;
    e[t >> 5] |= 128 << t % 32,
    e[14 + (t + 64 >>> 9 << 4)] = t;
    var s = 1732584193
      , c = -271733879
      , d = -1732584194
      , l = 271733878;
    for (n = 0; n < e.length; n += 16)
        i = s,
        r = c,
        a = d,
        o = l,
        s = h(s, c, d, l, e[n], 7, -680876936),
        l = h(l, s, c, d, e[n + 1], 12, -389564586),
        d = h(d, l, s, c, e[n + 2], 17, 606105819),
        c = h(c, d, l, s, e[n + 3], 22, -1044525330),
        s = h(s, c, d, l, e[n + 4], 7, -176418897),
        l = h(l, s, c, d, e[n + 5], 12, 1200080426),
        d = h(d, l, s, c, e[n + 6], 17, -1473231341),
        c = h(c, d, l, s, e[n + 7], 22, -45705983),
        s = h(s, c, d, l, e[n + 8], 7, 1770035416),
        l = h(l, s, c, d, e[n + 9], 12, -1958414417),
        d = h(d, l, s, c, e[n + 10], 17, -42063),
        c = h(c, d, l, s, e[n + 11], 22, -1990404162),
        s = h(s, c, d, l, e[n + 12], 7, 1804603682),
        l = h(l, s, c, d, e[n + 13], 12, -40341101),
        d = h(d, l, s, c, e[n + 14], 17, -1502002290),
        s = y(s, c = h(c, d, l, s, e[n + 15], 22, 1236535329), d, l, e[n + 1], 5, -165796510),
        l = y(l, s, c, d, e[n + 6], 9, -1069501632),
        d = y(d, l, s, c, e[n + 11], 14, 643717713),
        c = y(c, d, l, s, e[n], 20, -373897302),
        s = y(s, c, d, l, e[n + 5], 5, -701558691),
        l = y(l, s, c, d, e[n + 10], 9, 38016083),
        d = y(d, l, s, c, e[n + 15], 14, -660478335),
        c = y(c, d, l, s, e[n + 4], 20, -405537848),
        s = y(s, c, d, l, e[n + 9], 5, 568446438),
        l = y(l, s, c, d, e[n + 14], 9, -1019803690),
        d = y(d, l, s, c, e[n + 3], 14, -187363961),
        c = y(c, d, l, s, e[n + 8], 20, 1163531501),
        s = y(s, c, d, l, e[n + 13], 5, -1444681467),
        l = y(l, s, c, d, e[n + 2], 9, -51403784),
        d = y(d, l, s, c, e[n + 7], 14, 1735328473),
        s = S(s, c = y(c, d, l, s, e[n + 12], 20, -1926607734), d, l, e[n + 5], 4, -378558),
        l = S(l, s, c, d, e[n + 8], 11, -2022574463),
        d = S(d, l, s, c, e[n + 11], 16, 1839030562),
        c = S(c, d, l, s, e[n + 14], 23, -35309556),
        s = S(s, c, d, l, e[n + 1], 4, -1530992060),
        l = S(l, s, c, d, e[n + 4], 11, 1272893353),
        d = S(d, l, s, c, e[n + 7], 16, -155497632),
        c = S(c, d, l, s, e[n + 10], 23, -1094730640),
        s = S(s, c, d, l, e[n + 13], 4, 681279174),
        l = S(l, s, c, d, e[n], 11, -358537222),
        d = S(d, l, s, c, e[n + 3], 16, -722521979),
        c = S(c, d, l, s, e[n + 6], 23, 76029189),
        s = S(s, c, d, l, e[n + 9], 4, -640364487),
        l = S(l, s, c, d, e[n + 12], 11, -421815835),
        d = S(d, l, s, c, e[n + 15], 16, 530742520),
        s = A(s, c = S(c, d, l, s, e[n + 2], 23, -995338651), d, l, e[n], 6, -198630844),
        l = A(l, s, c, d, e[n + 7], 10, 1126891415),
        d = A(d, l, s, c, e[n + 14], 15, -1416354905),
        c = A(c, d, l, s, e[n + 5], 21, -57434055),
        s = A(s, c, d, l, e[n + 12], 6, 1700485571),
        l = A(l, s, c, d, e[n + 3], 10, -1894986606),
        d = A(d, l, s, c, e[n + 10], 15, -1051523),
        c = A(c, d, l, s, e[n + 1], 21, -2054922799),
        s = A(s, c, d, l, e[n + 8], 6, 1873313359),
        l = A(l, s, c, d, e[n + 15], 10, -30611744),
        d = A(d, l, s, c, e[n + 6], 15, -1560198380),
        c = A(c, d, l, s, e[n + 13], 21, 1309151649),
        s = A(s, c, d, l, e[n + 4], 6, -145523070),
        l = A(l, s, c, d, e[n + 11], 10, -1120210379),
        d = A(d, l, s, c, e[n + 2], 15, 718787259),
        c = A(c, d, l, s, e[n + 9], 21, -343485551),
        s = T(s, i),
        c = T(c, r),
        d = T(d, a),
        l = T(l, o);
    return [s, c, d, l]
}
function I(e) {
    var t, n = "", i = 32 * e.length;
    for (t = 0; t < i; t += 8)
        n += String.fromCharCode(e[t >> 5] >>> t % 32 & 255);
    return n
}
function m(e) {
    var t, n = [];
    for (n[(e.length >> 2) - 1] = void 0,
    t = 0; t < n.length; t += 1)
        n[t] = 0;
    var i = 8 * e.length;
    for (t = 0; t < i; t += 8)
        n[t >> 5] |= (255 & e.charCodeAt(t / 8)) << t % 32;
    return n
}
function C(e) {
    var t, n, i = "";
    for (n = 0; n < e.length; n += 1)
        t = e.charCodeAt(n),
        i += "0123456789abcdef".charAt(t >>> 4 & 15) + "0123456789abcdef".charAt(15 & t);
    return i
}
function N(e) {
    return unescape(encodeURIComponent(e))
}
function O(e) {
    return function(e) {
        return I(g(m(e), 8 * e.length))
    }(N(e))
}
function generate_access_key(e) {
    return C(O(e))
}


// request_id
function generate_request_id() {
    return (Math.random().toString(36) + "0000000000").substring(2, 2 + "0000000000".length)
}

function generate_long_request_id() {
    return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (function(e) {
            var t = 16 * Math.random() | 0;
            return ("x" === e ? t : 3 & t | 8).toString(16)
        }
    ))
}
// request_cid and session_id
function generate_request_cid() {
    let e = 10, t = undefined
    const n = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz".split("")
      , i = [];
    let r = null
      , a = null
      , o = null;
    const s = n.length;
    if (t = (t = t || s) > s ? s : t,
    e)
        for (r = 0; r < e; r++)
            o = 0 | Math.random() * t,
            i[r] = n[o];
    else
        for (i[8] = "-",
        i[13] = "-",
        i[18] = "-",
        i[23] = "-",
        i[14] = "4",
        r = 0; r < 36; r++)
            i[r] || (a = 0 | 16 * Math.random(),
            i[r] = n[19 === r ? 3 & a | 8 : a]);
    return i.join("")
}


function generate_csrf_token() {
    let e = "swp_csrf_token"
    let document = {
        cookie: "locale=zh-CN; _gcl_au=1.1.1773137480.1713790863; _ga=GA1.1.252483876.1713790863; _ga_VPYRHN104D=GS1.1.1713790863.1.1.1713790872.51.0.0; lang=zh; __tea__ug__uid=1007701713790873353; et=5149005c67cbe62db3d7f613bb9c7440; Hm_lvt_e78c0cb1b97ef970304b53d2097845fd=1716609558; i18n_locale=zh-CN; _csrf_token=36b375aad3381c672c2752df4c2f78c9bc1b51ae-1716787751; ccm_cdn_host=//lf-scm-cn.feishucdn.com; MONITOR_WEB_ID=eb362632-773d-4a6c-b3f7-fd69a73f80e1; msToken=1aL_Z6EfXm8A5YvLxai6CT2XUrk4rk-TS1Tr9VEIqx5dwdqXD_raGfMXYFZPQr3B_aVm00bKlLyYQ6fw2u-BHADiWT81bCZ2Vfft2Dm0_AzIVT8PUcoBPjUu0STE1Q==; swp_csrf_token=b2f409f7-fd71-4915-bf04-9248fcedd78d"
    }
    return decodeURIComponent(document.cookie.replace(new RegExp("(?:(?:^|.*;)\\s*".concat(encodeURIComponent(e).replace(/[-.+*]/g, "\\$&"), "\\s*\\=\\s*([^;]*).*$)|^.*$")), "$1")) || ""
}

