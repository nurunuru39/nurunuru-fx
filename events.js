// ===== 重要指標の日程(トップページと押し目スキャナーで共通) =====
// 日程を足すときは、このファイルの DATES だけ直せばOK。
// ・日付は「アメリカ東部時間の発表日」を 'YYYY-MM-DD' で書く。
// ・FOMC は会合の 2日目(政策金利が発表される日)を書く。
// ・発表時刻(東部時間)は TYPES に書いてある。日本時間は、アメリカの夏時間に合わせて自動で計算する。
(function () {
  var TYPES = {
    nfp:  { name: '雇用統計', full: 'アメリカの雇用統計',     et: '08:30' },
    cpi:  { name: 'CPI',      full: 'アメリカのCPI(消費者物価指数)', et: '08:30' },
    fomc: { name: 'FOMC',     full: 'FOMCの政策金利発表',     et: '14:00' }
  };

  var DATES = {
    // 雇用統計(アメリカ労働統計局 BLS の公式日程 https://www.bls.gov/schedule/news_release/empsit.htm)
    nfp: [
      // まだ入れていない(公式日程を確認してから入れる)
    ],
    // CPI(アメリカ労働統計局 BLS の公式日程 https://www.bls.gov/schedule/news_release/cpi.htm)
    cpi: [
      // まだ入れていない(公式日程を確認してから入れる)
    ],
    // FOMC(FRB の公式日程 https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm)
    fomc: [
      // まだ入れていない(公式日程を確認してから入れる)
    ]
  };

  // ---- ここから下は計算のしくみ(ふだんは触らなくてOK) ----

  // アメリカの夏時間:3月の第2日曜 2:00 から 11月の第1日曜 2:00 まで(2007年からのルール)
  function nthSunday(y, m, n) {            // m は 0=1月
    var first = new Date(Date.UTC(y, m, 1)).getUTCDay();
    return 1 + (7 - first) % 7 + (n - 1) * 7;
  }
  function isUsDst(y, m, d, hh) {
    var start = nthSunday(y, 2, 2), end = nthSunday(y, 10, 1);
    var md = m * 100 + d, s = 2 * 100 + start, e = 10 * 100 + end;
    if (md > s && md < e) return true;
    if (md === s) return hh >= 2;
    if (md === e) return hh < 2;
    return false;
  }
  // 東部時間の日付と時刻 → 本当の時刻(Date)
  function etToDate(ymd, hm) {
    var p = ymd.split('-').map(Number), t = hm.split(':').map(Number);
    var offset = isUsDst(p[0], p[1] - 1, p[2], t[0]) ? 4 : 5;   // 夏時間は UTC-4、冬時間は UTC-5
    return new Date(Date.UTC(p[0], p[1] - 1, p[2], t[0] + offset, t[1]));
  }

  var list = [];
  Object.keys(DATES).forEach(function (key) {
    DATES[key].forEach(function (ymd) {
      var ty = TYPES[key];
      list.push({ key: key, name: ty.name, full: ty.full, at: etToDate(ymd, ty.et) });
    });
  });
  list.sort(function (a, b) { return a.at - b.at; });

  var jst = function (d, o) { return new Intl.DateTimeFormat('ja-JP', Object.assign({ timeZone: 'Asia/Tokyo' }, o)).format(d); };

  window.NuruEvents = {
    list: list,
    // 日本時間の日付(YYYY/MM/DD)
    jstDay: function (d) { return jst(d, { year: 'numeric', month: '2-digit', day: '2-digit' }); },
    // 日本時間の時刻(例 22:30、4:00)
    jstTime: function (d) { return jst(d, { hour: 'numeric', minute: '2-digit' }); },
    // 日本時間で今日に発表がある指標
    today: function (now) {
      var k = this.jstDay(now || new Date());
      var self = this;
      return list.filter(function (e) { return self.jstDay(e.at) === k; });
    },
    // 発表の before 分前 〜 after 分後 に入っている指標
    around: function (now, before, after) {
      var t = (now || new Date()).getTime();
      return list.filter(function (e) { var x = e.at.getTime(); return t >= x - before * 6e4 && t <= x + after * 6e4; });
    },
    // いちばん最後の日程(日程の足し忘れチェック用)
    lastDate: list.length ? list[list.length - 1].at : null
  };
})();
