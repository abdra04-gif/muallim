var WIDGETS = __WIDGETS__;
var DATA = __DATA__;
var IMG = __IMG__;
var BARS = [8,16,20,11,18,9,16,13,20,10,15,7].map(function (h) { return '<i style="height:' + h + 'px"></i>'; }).join("");
var TX = {
  en: {ph: "Message", status: "bot", teacher: "teacher", only: "👁 only you can see this · disappears",
    lesson: "Lesson #", ruleHead: "Rule", stage2: "Stage II example",
    s1: "Look at the page, right to left.", s2: "Watch the video lesson: it comes next ⬇", s3: "Learn the new letters card by card, with the teacher's voice.",
    s4: "Check yourself: read the page aloud in one voice message.", r1: "This page explains a rule; there is nothing to read aloud.",
    r3: "Go through the rule with the book's words and one question.", learn: "📖 Learn step by step", checkNow: "🎤 Check myself now",
    ruleBtn: "📖 Understand the rule", video: "▶ Video", learnS: "📖 Learn", readHint: "🎤 Read the page aloud and send a voice message. I will listen and show what to repeat.",
    dWhere: "📍 Where the sounds are produced (from the book)", dVideo: "🎬 The book's video lesson", dVideoNote: "Opens at the minute where this page starts (start times set by a teacher).",
    dReal: "🎬 Pronunciation close up", dLive: "🧑‍🏫 A lesson with a live teacher", dLiveNote: "Online, 15–20 minutes: the teacher listens to your reading and corrects the articulation. Available at any time.",
    dLiveBtn: "📝 Ask for a teacher", dLiveOk: "Request sent. A teacher will message you in Telegram to agree on a time.",
    ruleHint: "This page explains a rule; nothing to read aloud.", noRead: "This page has nothing to read aloud. Tap “📖 Understand the rule”.",
    guess: "Checking your reading…", noVid: "A short video for this page is being chosen or recorded.", deeper: "Go deeper", real: "🎬 Pronunciation close up", live: "Want a live teacher? In Stage II.",
    prev: "← Lesson #", next: "Lesson # →", list: "📚 Lessons", home: "🏠",
    yt: "YouTube", ytNote: "Full lesson, # min. We open it at the minute where this page's letters start (start time set by the teacher).",
    playerNote: "In Telegram the video plays right inside the app, with picture-in-picture. This review page cannot embed YouTube, so open it there:",
    openYt: "Open on YouTube ↗", close: "Close",
    d1: "🎧 Listening to your reading…", d2: "🔎 Comparing # words with the book…", d3: "✍️ Writing your feedback…", stop: "■ Stop",
    stopped: "Stopped. Read the page again whenever you are ready.", quote: "Lesson #", again: "Read the page once more and send a new voice message 🎤",
    done3: "MashaAllah! Lessons 1–3 are complete.", nextPage: "Next comes the following page of the book, in the same way.",
    demoOnly: "In this demo lessons 1–3 are open. In the bot, this lesson opens the same way.", st2: "Stage II opens: articulation, videos of real teachers and an online teacher.",
    skipped: "OK: marked as viewed. You can read it aloud any time.", langSet: "Language: English.", kk: "Қазақша is a draft under review; the bot stays in Russian for now.",
    remSet: "🔔 Reminder at #. It will look like this: “Assalamu alaikum! Lesson # is waiting for you, five minutes are enough.” No reproaches, no “lost streak”.",
    why: "You read # on page # and # was heard. Let's listen to it again.", whyNew: "A syllable from the letters you have learned.",
    hListDemo: "The demo opens lessons 1–15 (all 28 letters) and pages 49–50; feedback with errors is shown in lessons 1–3.", remOff: "🔔 Reminder is off.", delAsk: "🗑 This deletes your recordings and progress for good. In the bot you confirm it with one more button.",
    opOn: "🌙 From tomorrow the first session of the day starts with isti'adha and basmala.", opOff: "🌙 Sessions start straight with the lesson.",
    bigSet: "🔎 Letters on the cards are now larger.", recOff: "🎙 Your new recordings will not be kept. Feedback still works.", recOn: "🎙 Your recordings are kept under a pseudonym.",
    dispute: "Thank you! A teacher will listen to this attempt. It is not counted against you.",
    hidden: "listen", more: "⋯ More", mHelp: "❓ How to study", mSheet: "📋 Letter sheet", mRem: "🔔 Reminder", mData: "🔒 My data",
    help: "One lesson = one page: 1) look at the page, 2) watch the video, 3) learn the cards, 4) read the page aloud, 5) read the feedback. That's all.",
    sheet: "The alphabet, as printed on page 10 of the book:", rem: "🔔 A reminder comes every day at 19:00. Change the time or turn it off in “More”.",
    data: "🔒 Your recordings are stored under a pseudonym for the research. You can stop recording or delete everything at any time.",
    tRich: "Rich message", tWidget: "Interactive message", tUpd: "updates in place", tEph: "Ephemeral reply", tDraft: "Live draft", tQuote: "Quotes the lesson",
    tVoice: "Voice message", tDis: "Disabled button", tLink: "Link preview · YouTube", tGame: "Quiz",
    hStart: "Tap “Lesson 1”.", hLesson: "▶ Video, 📖 Learn, or just tap 🎤 and read the page.", hCard: "Tap syllables to hear the teacher; “Next ›” changes the card in place.",
    hMic: "Tap 🎤 below to send your reading whenever you are ready.", hFb: "Tap 🔊 to hear the teacher, then “Next →”.", hRule: "Go through the rule cards and answer the question.",
    hList: "Tap a lesson to open it.", hRev: "Tap 🔊 to hear a syllable, then choose it.", hHome: "Continue, or open Lessons, Review, Progress or Settings."},
  ru: {ph: "Сообщение", status: "бот", teacher: "учитель", only: "👁 видно только вам · исчезнет",
    lesson: "Урок #", ruleHead: "Правило", stage2: "Этап II",
    s1: "Посмотрите на страницу, справа налево.", s2: "Посмотрите видеоурок — он следующим сообщением ⬇", s3: "Выучите новые буквы по карточкам, с голосом учителя.",
    s4: "Проверь себя: прочитайте страницу вслух одним голосовым.", r1: "На этой странице правило, читать вслух не нужно.",
    r3: "Разберите правило словами книги и ответьте на вопрос.", learn: "📖 Учить по шагам", checkNow: "🎤 Сразу проверить себя",
    ruleBtn: "📖 Разобрать правило", video: "▶ Видео", learnS: "📖 Учить", readHint: "🎤 Прочитайте страницу вслух и отправьте голосовое. Я послушаю и подскажу, что повторить.",
    dWhere: "📍 Где рождаются звуки (из книги)", dVideo: "🎬 Видеоурок к книге", dVideoNote: "Открывается с минуты, где начинается эта страница (отметки ставит учитель).",
    dReal: "🎬 Произношение крупным планом", dLive: "🧑‍🏫 Занятие с живым учителем", dLiveNote: "Онлайн, 15–20 минут: учитель послушает ваше чтение и поправит произношение. Доступно в любой момент.",
    dLiveBtn: "📝 Попросить учителя", dLiveOk: "Заявка отправлена. Учитель напишет вам в Telegram, чтобы договориться о времени.",
    ruleHint: "На этой странице правило, читать вслух не нужно.", noRead: "На этой странице нечего читать вслух. Нажмите «📖 Разобрать правило».",
    guess: "Проверяю чтение…", noVid: "Короткое видео к этой странице подбирается или записывается.", deeper: "Углублённо", real: "🎬 Произношение крупным планом", live: "Хотите живого учителя? На Этапе II.",
    prev: "← Урок #", next: "Урок # →", list: "📚 Уроки", home: "🏠",
    yt: "YouTube", ytNote: "Полный урок, # мин. Открываем с минуты, где начинаются буквы этой страницы (отметку ставит учитель).",
    playerNote: "В Telegram видео играет прямо в приложении. Эта страница не может встроить YouTube, поэтому откройте его там:",
    openYt: "Открыть на YouTube ↗", close: "Закрыть",
    d1: "🎧 Слушаю ваше чтение…", d2: "🔎 Сравниваю # слов с книгой…", d3: "✍️ Пишу разбор…", stop: "■ Стоп",
    stopped: "Остановлено. Прочитайте страницу ещё раз, когда будете готовы.", quote: "Урок #", again: "Прочитайте страницу ещё раз и пришлите новое голосовое 🎤",
    done3: "МашаАллах! Уроки 1–3 пройдены.", nextPage: "Дальше — следующая страница книги, так же.",
    demoOnly: "В демо открыты уроки 1–3. В боте этот урок откроется так же.", st2: "Этап II открыт: артикуляция, видео с живыми учителями и онлайн-учитель.",
    skipped: "Хорошо: отмечено как просмотренное. Прочитать вслух можно в любой момент.", langSet: "Язык: русский.", kk: "Қазақша — черновик на проверке; пока бот говорит по-русски.",
    remSet: "🔔 Напоминание в #. Выглядит так: «Ассаляму алейкум! Урок # ждёт вас, хватит пяти минут». Без упрёков и «потерянной серии».",
    why: "Вы читали # на стр. # — прозвучало #. Послушаем ещё раз.", whyNew: "Слог из букв, которые вы уже прошли.",
    hListDemo: "В демо открыты уроки 1–15 (все 28 букв) и страницы 49–50; разбор с ошибками — на уроках 1–3.", remOff: "🔔 Напоминание выключено.", delAsk: "🗑 Это удалит ваши записи и прогресс насовсем. В боте нужно подтвердить ещё одной кнопкой.",
    opOn: "🌙 Со завтрашнего дня первое занятие начнётся с истиазы и басмалы.", opOff: "🌙 Занятие начинается сразу с урока.",
    bigSet: "🔎 Буквы на карточках теперь крупнее.", recOff: "🎙 Новые записи не будут сохраняться. Разбор работает как прежде.", recOn: "🎙 Записи сохраняются под псевдонимом.",
    dispute: "Спасибо! Учитель прослушает эту попытку. На ваш прогресс это не влияет.",
    hidden: "послушайте", more: "⋯ Ещё", mHelp: "❓ Как заниматься", mSheet: "📋 Шпаргалка букв", mRem: "🔔 Напоминание", mData: "🔒 Мои данные",
    help: "Один урок — одна страница: 1) посмотрите страницу, 2) видео, 3) карточки, 4) прочитайте страницу вслух, 5) разбор. Вот и всё.",
    sheet: "Алфавит — как на странице 10 книги:", rem: "🔔 Напоминание приходит каждый день в 19:00. Время можно изменить или выключить в «Ещё».",
    data: "🔒 Ваши записи хранятся под псевдонимом для исследования. Запись можно запретить или удалить всё в любой момент.",
    tRich: "Rich message", tWidget: "Interactive message", tUpd: "updates in place", tEph: "Ephemeral reply", tDraft: "Live draft", tQuote: "Quotes the lesson",
    tVoice: "Voice message", tDis: "Disabled button", tLink: "Link preview · YouTube", tGame: "Quiz",
    hStart: "Tap “Урок 1”.", hLesson: "▶ Видео, 📖 Учить, or just tap 🎤 and read the page.", hCard: "Tap syllables to hear the teacher; “Далее ›” changes the card in place.",
    hMic: "Tap 🎤 below to send your reading whenever you are ready.", hFb: "Tap 🔊 to hear the teacher, then “Дальше →”.", hRule: "Go through the rule cards and answer the question.",
    hList: "Tap a lesson to open it.", hRev: "Tap 🔊 to hear a syllable, then choose it.", hHome: "Continue, or open Уроки, Повторить, Прогресс or Настройки."}
};
function f(s) { var a = arguments, i = 1; return s.replace(/#/g, function () { return a[i++]; }); }
function esc(s) { var d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

/* run a widget's real code with a stand-in for Telegram */
function mount(host, state, onRequest) {
  var root = host.attachShadow({mode: "open"});
  var tpl = document.createElement("template");
  tpl.innerHTML = WIDGETS[host.dataset.w];
  var scripts = Array.prototype.slice.call(tpl.content.querySelectorAll("script"));
  var code = scripts.map(function (s) { return s.textContent; }).join("\n");
  scripts.forEach(function (s) { s.remove(); });
  root.appendChild(tpl.content);
  var handlers = [];
  var T = {chatData: JSON.stringify(state), isPreview: false,
    onEvent: function (n, fn) { if (n === "chatDataChanged") { handlers.push(fn); } },
    request: function (d) { return new Promise(function (ok) { setTimeout(function () { if (onRequest) { onRequest(d); } ok({result: null}); }, 200); }); },
    HapticFeedback: {impactOccurred: function () {}, selectionChanged: function () {}, notificationOccurred: function () {}}};
  var doc = {getElementById: function (id) { return root.getElementById(id); }, createElement: function (t) { return document.createElement(t); },
    createTextNode: function (t) { return document.createTextNode(t); }};
  try { new Function("window", "document", "matchMedia", code)({TelegramWidget: T}, doc, window.matchMedia.bind(window)); }
  catch (e) { host.textContent = "Widget error: " + e.message; }
  return function (patch) { Object.assign(state, patch); T.chatData = JSON.stringify(state); handlers.forEach(function (fn) { fn(); }); };
}
document.addEventListener("click", function (e) {
  var img = e.target.closest("img[data-zoom]");
  if (img) { var z = document.createElement("div"); z.className = "zoom"; z.innerHTML = '<img alt="Book page" src="' + img.src + '">'; z.onclick = function () { z.remove(); }; document.body.appendChild(z); return; }
  var th = e.target.closest("[data-vids]");
  if (th) { openPlayer(DATA.lessons[+th.dataset.vids].videos, "en"); }
});
function openPlayer(videos, lg) {
  var T = TX[lg], v = videos[0], p = document.createElement("div"); p.className = "player";
  var more = videos.slice(1).map(function (x) { return '<a href="https://www.youtube.com/watch?v=' + x.id + '" target="_blank" rel="noopener" style="background:#333">' + esc(x.title) + "</a>"; }).join(" ");
  p.innerHTML = '<div class="box"><div class="sc"><img alt="" src="' + IMG["yt-" + v.id] + '"><i>▶</i></div><div class="bar2"><b></b></div><p><b>' + esc(v.title) + "</b> · " + v.minutes + " min</p><p>" + T.playerNote +
    '</p><a href="https://www.youtube.com/watch?v=' + v.id + '" target="_blank" rel="noopener">' + T.openYt + "</a>" + more + '<button type="button">' + T.close + "</button></div>";
  p.querySelector("button").onclick = function () { p.remove(); };
  p.addEventListener("click", function (e) { if (e.target === p) { p.remove(); } });
  document.body.appendChild(p);
}

/* ---------- message builders (simulator and static gallery) ---------- */
function Chat(box, tx, lang, opts) { this.box = box; this.t = tx; this.lang = lang; this.live = !!opts.live; this.timers = []; this.onReq = opts.onReq || function () {}; }
Chat.prototype.later = function (fn, ms) { this.timers.push(setTimeout(fn, ms)); };
Chat.prototype.scroll = function (m) {
  if (!this.live) { return; }
  var b = this.box;
  this.later(function () { b.scrollTop = m && m.offsetHeight > b.clientHeight * 0.6 ? m.offsetTop - 34 : b.scrollHeight; }, 40);
};
Chat.prototype.tag = function (text, me) { if (!text) { return; } var g = document.createElement("div"); g.className = "tag" + (me ? " me" : ""); g.textContent = text; this.box.appendChild(g); };
Chat.prototype.bubble = function (html, cls, tag) { this.tag(tag, cls === "me"); var m = document.createElement("div"); m.className = "msg" + (cls ? " " + cls : ""); m.innerHTML = html; this.box.appendChild(m); this.scroll(m); return m; };
Chat.prototype.text = function (h) { return this.bubble('<div class="txt">' + h + "</div>"); };
Chat.prototype.widget = function (name, state, tag, before) {
  var self = this, m = this.bubble((before || "") + '<div class="wb" data-w="' + name + '"></div>', "", tag);
  var set = mount(m.querySelector(".wb"), state, function (d) { self.onReq(name, d, set, state, m); });
  if (this.live) { this.later(function () { self.scroll(m); }, 400); }
  return {set: set, msg: m, state: state};
};
Chat.prototype.voice = function (label, me, eph) {
  var T = this.t, m = this.bubble((eph ? "<em>" + T.only + "</em>" : "") + '<div class="voice"><div class="p">▶</div><div class="w">' + BARS + "</div><small>" + label + "</small></div>", me ? "me" : (eph ? "eph" : ""), eph ? T.tEph : (me ? T.tVoice : ""));
  if (eph && this.live) {
    this.later(function () { m.classList.add("gone"); }, 6500);
    this.later(function () { if (m.previousSibling && m.previousSibling.className === "tag") { m.previousSibling.remove(); } m.remove(); }, 7200);
  }
  return m;
};
Chat.prototype.video = function (v) {
  var T = this.t;
  return this.bubble('<div class="lp"><small>' + T.yt + "</small><b>" + esc(v.title) + '</b><button class="th" data-yt="' + v.id + '" data-title="' + esc(v.title) + '" data-lang="' + this.lang + '"><img alt="" src="' + IMG["yt-" + v.id] + '"><span><i>▶</i></span><em>' + v.minutes + ":00</em></button><p>" + f(T.ytNote, v.minutes) + "</p></div>", "", T.tLink);
};
Chat.prototype.eph = function (html) {
  var m = this.bubble("<em>" + this.t.only + '</em><div class="txt">' + html + "</div>", "eph", this.t.tEph);
  if (this.live) { this.later(function () { m.classList.add("gone"); }, 5500); this.later(function () { if (m.previousSibling && m.previousSibling.className === "tag") { m.previousSibling.remove(); } m.remove(); }, 6200); }
  return m;
};
/* ---------- texts added in the November review ---------- */
Object.assign(TX.ru, {
  book: "Книга", tapSyl: "Нажмите на слог — сразу прозвучит голос чтеца", back: "‹ Назад", nextC: "Далее ›", toRead: "🎤 К чтению ›",
  cardN: "# из #", partOf: "Часть # из #", letterX: "буква #", readAll: "Читаем вслух", min: "мин",
  line1: "На странице это строка #.", lineN: "На странице это строки #–#.", readHint2: "Прочитайте вслух: нажмите и держите значок микрофона справа от поля «Сообщение», отпустите — голосовое уйдёт.",
  unsure: "Не уверены в слоге? В «📖 Учить буквы» каждый слог можно послушать.", learnL: "📖 Учить буквы", lessons: "📚 Уроки",
  vAll: "✅ Прочитано! Все слова верно: #", vMost: "👍 Прочитано: # из # слов верно", repeat: "Прочитано неверно:",
  right: "как правильно", heard: "так прозвучало", partNext: "Часть # ›", lessonNext: "Урок # ›", againB: "🔄 Ещё раз", botErr: "🚩 Бот ошибся", homeB: "🏠 На главную",
  again: "Прочитайте эту часть ещё раз и пришлите новое голосовое 🎤",
  lessonDone: "🌟 Урок # пройден! Буквы # теперь в закреплении — я позову их повторить завтра.",
  dAsk: "Что не так?", dR: ["Я прочитал(а) правильно", "Ошибка указана не та", "Бот плохо расслышал (шум, тихо)", "Другое"], dWord: "В каком слове?",
  dThanks: "Спасибо! Учитель прослушает эту запись. На ваш прогресс это не влияет.", cancel: "Отмена",
  noSnd: "Записи этого слога пока нет — её запишет учитель.",
  intro: "Часть 1 — вступление книги (стр. 5–9): как устроен учебник и видеоуроки. Читать вслух там нечего, уроки начинаются со страницы 10.", introT: "Введение",
  name: "название", trio: "все три", listen: "послушать", openL: "📖 Урок #", letterH: "Буква # · урок #",
  str: "Повторение: # · #", strNew: "ещё не изучена", strDue: "пора повторить", strIn: "повтор через # дн.",
  rvH: "🔁 Повторение", rvHear: "Послушайте и выберите слог", rvMark: "Какая здесь огласовка?", rvFind: "В каком слове есть буква #?",
  rvErr: "Это слово вы прочитали с ошибкой. Какая огласовка над #?", vn: ["фатха", "кясра", "дамма"],
  shape: ["чёрточка над буквой", "чёрточка под буквой", "маленький و над буквой"], isV: "Это # — #.", isS: "Это #.", inW: "Буква # — в слове #.",
  combo: "🔥 # подряд", rvOk: "✅ Верно!", rvNo: "Не совсем.", rvNext: "Дальше ›", rvEnd: "Готово: # из # верно", rvMore: "🔁 Ещё раунд",
  rvNone: "Пока нечего повторять: прочитайте вслух урок 1 — и его буквы появятся здесь.", rvFree: "Сегодня по плану повторять нечего — потренируем пройденные буквы.",
  rvLetters: "Как теперь держатся буквы:", dayP: "⏩ Прошёл день. Буквы, которые пора повторить, отмечены 🔁 на карте.",
  data: "🔒 Ваши ответы и записи сохраняются: так учитель видит ваш прогресс и может помочь. Подробнее — /privacy.",
  tVb: "Voice blocks", tEdit: "edited in place",
  hStart: "First contact: the language, then one tap to agree to the data use. Then the home screen: one big button, “Start with the alphabet” for a newcomer, “Continue: lesson N” later.",
  hLesson: "Watch the video, then send a voice message reading the words. Everything else is under 📖 Go deeper.", hCard: "Tap a syllable: the reciter's voice plays at once. “Далее ›” edits the card in place.",
  hFb: "Tap ▶ to hear how it should sound, then go to the next part.", hRev: "Answer: letters you get right come back later and later.",
  hHome: "Tap a letter on the map, Continue, or open Уроки, Повторить, Прогресс, Настройки.", hMic: "Tap 🎤 below to send your reading of this part."
});
Object.assign(TX.en, {
  book: "Book", tapSyl: "Tap a syllable to hear the reciter at once", back: "‹ Back", nextC: "Next ›", toRead: "🎤 To reading ›",
  cardN: "# of #", partOf: "Part # of #", letterX: "letter #", readAll: "Read aloud", min: "min",
  line1: "On the page this is line #.", lineN: "On the page these are lines #–#.", readHint2: "Read aloud: press and hold the microphone icon to the right of the “Message” field; release to send.",
  unsure: "Unsure of a syllable? In “📖 Learn the letters” every syllable can be heard.", learnL: "📖 Learn the letters", lessons: "📚 Lessons",
  vAll: "✅ Read! All words correct: #", vMost: "👍 Read: # of # words correct", repeat: "Read incorrectly:",
  right: "how it sounds", heard: "what was heard", partNext: "Part # ›", lessonNext: "Lesson # ›", againB: "🔄 Again", botErr: "🚩 Bot was wrong", homeB: "🏠 Home",
  again: "Read this part once more and send a new voice message 🎤",
  lessonDone: "🌟 Lesson # done! The letters # are now in review; I will call them back tomorrow.",
  dAsk: "What is wrong?", dR: ["I read it correctly", "The wrong error is shown", "The bot heard badly (noise, quiet)", "Other"], dWord: "Which word?",
  dThanks: "Thank you! A teacher will listen to this recording. It does not affect your progress.", cancel: "Cancel",
  noSnd: "There is no recording of this syllable yet; a teacher will record it.",
  intro: "Part 1 is the book's introduction (pp. 5–9): how the book and the video lessons work. Nothing to read aloud; lessons start on page 10.", introT: "Introduction",
  name: "name", trio: "all three", listen: "listen", openL: "📖 Lesson #", letterH: "Letter # · lesson #",
  str: "Review: # · #", strNew: "not learned yet", strDue: "time to review", strIn: "next review in # days",
  rvH: "🧠 Review", rvHear: "Listen and choose the syllable", rvMark: "Which vowel mark is this?", rvFind: "Which word has the letter #?",
  rvErr: "You misread this word. Which vowel mark is on #?", vn: ["fatha", "kasra", "damma"],
  shape: ["a stroke above the letter", "a stroke below the letter", "a small و above the letter"], isV: "This is #: #.", isS: "This is #.", inW: "The letter # is in #.",
  combo: "🔥 # in a row", rvOk: "✅ Right!", rvNo: "Not quite.", rvNext: "Next ›", rvEnd: "Done: # of # correct", rvMore: "🔁 Another round",
  rvNone: "Nothing to review yet: read lesson 1 aloud and its letters will appear here.", rvFree: "Nothing is due today, so let's practise the letters you know.",
  rvLetters: "How the letters hold now:", dayP: "⏩ A day has passed. Letters due for review are marked 🔁 on the map.",
  data: "🔒 Your answers and recordings are kept so that a teacher can see your progress and help. More: /privacy.",
  tVb: "Voice blocks", tEdit: "edited in place",
  hStart: "First contact: the language, then one tap to agree to the data use. Then the home screen: one big button, “Start with the alphabet” for a newcomer, “Continue: lesson N” later.",
  hLesson: "Watch the video, then send a voice message reading the words. Everything else is under 📖 Go deeper.", hCard: "Tap a syllable: the reciter's voice plays at once. “Next ›” edits the card in place.",
  hFb: "Tap ▶ to hear how it should sound, then go to the next part.", hRev: "Answer: letters you get right come back later and later.",
  hHome: "Tap a letter on the map, Continue, or open Lessons, Review, Progress, Settings.", hMic: "Tap 🎤 below to send your reading of this part."
});

Object.assign(TX.ru, {
  teachV: "▶ Как произносит учитель — видеоурок", vidBtn: "▶ Видео · # мин", need: "нужно", heard: "прозвучало",
  readHint2: "Прочитайте эти строки книги вслух: нажмите и держите значок микрофона справа от поля «Сообщение», отпустите — голосовое уйдёт.", unsure: "Не уверены? «▶ Видео»: учитель разбирает эти буквы.",
  str: "Повторение: #", strNew: "ещё не изучена", strDue: "пора повторить сегодня", strIn: "через # дн.", today: "сегодня", inD: "через # дн.",
  rvH: "🔁 Закрепить", fixH: "🔁 Закрепить", fixDue: "Сегодня пора закрепить букв: #. Это шесть коротких вопросов.", fixNone: "Сегодня по плану закреплять нечего — можно потренировать пройденные буквы.",
  fixRule: "Пройденная буква возвращается через 1, 3, 7, 14 и 30 дней; ошибка в ней — снова через день.", fixGo: "▶ Начать", histB: "📜 История",
  rvLetters: "Когда буквы вернутся:", hRev: "Answer; letters you get right come back later and later.",
  hCard: "Cards change in place. The teacher's voice is in the video lesson; no synthetic sound."
});
Object.assign(TX.en, {
  teachV: "▶ How the teacher says it: video lesson", vidBtn: "▶ Video · # min", need: "needed", heard: "heard",
  readHint2: "Read these lines of the book aloud: press and hold the microphone icon to the right of the “Message” field; release to send.", unsure: "Unsure? “▶ Video”: the teacher goes through these letters.",
  str: "Review: #", strNew: "not learned yet", strDue: "due today", strIn: "in # days", today: "today", inD: "in # days",
  rvH: "🔁 Strengthen", fixH: "🔁 Strengthen", fixDue: "Letters due today: #. Six short questions.", fixNone: "Nothing is due today; you can still practise the letters you know.",
  fixRule: "A learned letter comes back after 1, 3, 7, 14 and 30 days; a mistake brings it back the next day.", fixGo: "▶ Start", histB: "📜 History",
  rvLetters: "When the letters come back:", hRev: "Answer; letters you get right come back later and later.",
  hCard: "Cards change in place. The teacher's voice is in the video lesson; no synthetic sound."
});

Object.assign(TX.ru, {mHead: "🎬 Посмотрите перед чтением", mBook: "Урок по книге", mBookSub: "учитель читает строки этой буквы · 1–5 мин", dLong: "🎓 Видеокурс по книге · musulmanin.com (16 уроков по ≈30 мин)", mWhole: "весь урок, # мин", mSeg: "фрагмент этой страницы",
  mSw: "Как произносится #", mSwSub: "д-р Айман Сувейд · коротко", mSwLong: "д-р Айман Сувейд · урок", mLesson: "урок"});
Object.assign(TX.en, {mHead: "🎬 Watch before reading", mBook: "The book's lesson", mBookSub: "a teacher reads this letter's lines · 1–5 min", dLong: "🎓 The book's video course · musulmanin.com (16 lessons, ≈30 min each)", mWhole: "whole lesson, # min", mSeg: "this page's fragment",
  mSw: "How # is pronounced", mSwSub: "Dr. Ayman Swaid · short", mSwLong: "Dr. Ayman Swaid · lesson", mLesson: "lesson"});
Object.assign(TX.ru, {readHint2: "Прочитайте вслух: нажмите и держите значок микрофона справа от поля «Сообщение», отпустите — голосовое уйдёт.",
  hFb: "Compare “нужно” and “прозвучало”, then go to the next part.", hHome: "Tap Start or Continue; Уроки, Повторение, Прогресс, Настройки are below."});
Object.assign(TX.en, {readHint2: "Read aloud: press and hold the microphone icon to the right of the “Message” field; release to send.",
  hFb: "Compare “needed” and “heard”, then go to the next part.", hHome: "Tap a letter on the map, Continue, or open Lessons, Strengthen, Progress, Settings."});
Object.assign(TX.ru, {
  vTitle: "▶ Видеокурс по книге", vShort: "короткий ролик · YouTube Shorts", vSmall: "🎬 Произношение крупным планом", vSeg: "фрагмент #–# · откроется и остановится на нём", vNoSeg: "# мин · объясняет звуки этих букв, строки страницы не читает",
  noVid: "🎬 Видео к этой странице подбирается.", line1: "строка # на странице", lineN: "строки #–# на странице",
  readHint2: "Прочитайте эти строки книги вслух: нажмите и держите значок микрофона справа от поля «Сообщение», отпустите — голосовое уйдёт.", anyPart: "Части можно читать в любом порядке и переключать выше.",
  dCards: "🃏 Карточки букв: слова книги, где рождается звук, слоги", autoNote: "В демо пример разбора с ошибками показан на уроках 1–3.",
  rvErr: "Это слово вы прочитали с ошибкой. Как оно написано в книге?", rvErr2: "Вы прочитали: #", rvLook: "Где буква #?", rvMark: "В каком слоге #?",
  lookWhy: "У # — #. А у остальных: #.", markWhy: "# — #: #.",
  introT: "Введение", introH: "📖 О книге", introGo: "▶ Алфавит",
  introHtml: "<p>Книга <b>«Муаллим сани»</b> Ахмадхади Максуди (1868–1941) больше ста лет учит мусульман читать Коран. Это издание опирается на Коран мединского издания.</p>" +
    "<p><b>Из чего состоит книга:</b></p><ol><li>Арабский алфавит — буквы и огласовки. С него начинаем.</li><li>Правила таджвида.</li><li>Короткие суры Корана.</li></ol>" +
    "<p><b>Как с ней заниматься:</b> к книге есть 16 видеоуроков, а книга помогает закрепить то, что показал учитель. Самое ценное — услышать произношение «из уст учителя». Поэтому в каждом уроке есть видео.</p>" +
    "",
  helpGo: "▶ Продолжить урок",
  helpHtml: "<p><b>Сначала — алфавит,</b> потом уроки: в каждом 1–3 новые буквы. Этап I — алфавит и 15 уроков: все 28 букв с огласовками.</p>" +
    "<ol><li><b>Посмотрите видео.</b> Над строками — короткий урок по книге (1–5 мин) и ролик «Как произносится» от д-ра Аймана Сувейда.</li>" +
    "<li><b>Прочитайте часть вслух.</b> Бот показывает строки книги — не больше двух за раз. Нажмите и держите значок микрофона справа от поля «Сообщение», прочитайте и отпустите.</li>" +
    "<li><b>Посмотрите разбор.</b> Зелёные слова — верно, жёлтые — стоит повторить: рядом написано, что нужно и что прозвучало. Идеально читать не обязательно.</li>" +
    "<li><b>Дальше.</b> Следующая часть, следующий урок — или «🔄 Ещё раз».</li></ol>" +
    "<p><b>Урок засчитан</b>, когда каждая часть прочитана один раз — с любым результатом. Все уроки открыты всегда: можно вернуться, пропустить, идти в своём темпе.</p>" +
    "<p><b>🔁 Закрепить.</b> Пройденные буквы возвращаются через 1, 3, 7, 14 и 30 дней — шесть коротких вопросов. Ошибки из ваших чтений попадают туда же.</p>" +
    "<p><b>Сколько заниматься.</b> 10–15 минут каждый день полезнее, чем час раз в неделю.</p>"
});
Object.assign(TX.en, {
  vTitle: "▶ The book's video course", vShort: "a short video · YouTube Shorts", vSmall: "🎬 Pronunciation close up", vSeg: "fragment #–# · opens and stops there", vNoSeg: "# min · explains these sounds, does not read the page lines",
  noVid: "🎬 A video for this page is being chosen.", line1: "line # on the page", lineN: "lines #–# on the page",
  readHint2: "Read these lines of the book aloud: press and hold the microphone icon to the right of the “Message” field; release to send.", anyPart: "Parts can be read in any order; switch them above.",
  dCards: "🃏 Letter cards: the book's words, where the sound is made, syllables", autoNote: "In the demo, feedback with errors is shown in lessons 1–3.",
  rvErr: "You misread this word. How is it written in the book?", rvErr2: "You read: #", rvLook: "Which is the letter #?", rvMark: "Which syllable has #?",
  lookWhy: "# has #. The others: #.", markWhy: "#: #, as in #.",
  introT: "Introduction", introH: "📖 About the book", introGo: "▶ The alphabet",
  introHtml: "<p><b>al-Muallim ath-Thani</b> by Ahmadhadi Maksudi (1868–1941) has taught Muslims to read the Quran for more than a century. This edition follows the Medina mushaf.</p>" +
    "<p><b>The book has three parts:</b></p><ol><li>The Arabic alphabet: letters and vowel marks. We start here.</li><li>Tajwid rules.</li><li>Short surahs.</li></ol>" +
    "<p><b>How to study with it:</b> the book comes with 16 video lessons and helps to consolidate what the teacher shows. Hearing the sounds “from the teacher's lips” is the most valuable part, so every lesson has a video.</p>" +
    "",
  helpGo: "▶ Continue the lesson",
  helpHtml: "<p><b>First the alphabet,</b> then lessons with 1–3 new letters each. Stage I is the alphabet and 15 lessons: all 28 letters with vowel marks.</p>" +
    "<ol><li><b>Watch the video.</b> Above the lines: a short lesson by the book (1–5 min) and “How it is pronounced” by Dr. Ayman Swaid.</li>" +
    "<li><b>Read a part aloud.</b> The bot shows the book's lines, at most two at a time. Press and hold the microphone icon next to the “Message” field, read, and release.</li>" +
    "<li><b>Look at the feedback.</b> Green words are right, gold ones are worth repeating, with what was needed and what was heard. Perfection is not required.</li>" +
    "<li><b>Go on.</b> The next part, the next lesson, or “🔄 Again”.</li></ol>" +
    "<p><b>A lesson counts</b> once every part has been read once, whatever the result. All lessons are always open.</p>" +
    "<p><b>🔁 Strengthen.</b> Learned letters come back after 1, 3, 7, 14 and 30 days: six short questions, including your own misread words.</p>" +
    "<p><b>How much.</b> 10–15 minutes every day helps more than an hour once a week.</p>"
});
Object.assign(TX.ru, {cta: "🎙 Запишите аудио для проверки произношения — прочитайте вслух:", vcTitle: "▶ Видеоурок", vcSub: "учитель читает эти слова",
  extraT: "📖 Углублённо", xPage: "📖 Страница книги", xSw: "🗣 Как произносятся буквы · д-р Айман Сувейд"});
Object.assign(TX.en, {cta: "🎙 Record an audio to check your pronunciation — read aloud:", vcTitle: "▶ Video lesson", vcSub: "a teacher reads these words",
  extraT: "📖 Go deeper", xPage: "📖 The book page", xSw: "🗣 How the letters are pronounced · Dr. Ayman Swaid"});
Object.assign(TX.ru, {alphaT: "Алфавит", ctaA: "🎙 Запишите аудио: назовите буквы по порядку, справа налево:", vcAlpha: "▶ Видеоурок: арабский алфавит",
  vcAlphaSub: "урок 1 видеокурса по книге · # мин", vAlpha: "✅ Записано! Весь алфавит прочитан"});
Object.assign(TX.en, {alphaT: "The alphabet", ctaA: "🎙 Record an audio: name the letters in order, right to left:", vcAlpha: "▶ Video lesson: the Arabic alphabet",
  vcAlphaSub: "lesson 1 of the book's video course · # min", vAlpha: "✅ Recorded! The whole alphabet is read"});
Object.assign(TX.ru, {abcHint: "Нажмите на букву — откроется её карточка. 🔁 — пора повторить.", abcRep: "▶ Повторить алфавит"});
Object.assign(TX.en, {abcHint: "Tap a letter to open its card. 🔁 means time to review.", abcRep: "▶ Review the alphabet"});
Object.assign(TX.ru, {ctaA: "👀 Это все 28 букв. Записывать ничего не нужно — просто посмотрите. Учить будем по одной, начиная с урока 1.",
  alphaGo: "▶ Начать урок 1", alphaNoRec: "Здесь записывать не нужно — это знакомство с буквами. Нажмите «▶ Начать урок 1».",
  micHow: "Как записать: нажмите и держите значок микрофона справа внизу, прочитайте, отпустите. Если включилась камера — нажмите на значок один раз, он сменится на микрофон.",
  unsureA: "🤔 Не расслышал чётко. Прочитайте эти строки ещё раз — чуть громче и не спеша.", hearT: "🔊 Как читает учитель"});
Object.assign(TX.en, {ctaA: "👀 These are all 28 letters. Nothing to record: just look. We learn them one by one, starting with lesson 1.",
  alphaGo: "▶ Start lesson 1", alphaNoRec: "Nothing to record here: this is a first look at the letters. Tap “▶ Start lesson 1”.",
  micHow: "How to record: press and hold the microphone icon at the bottom right, read, release. If the camera turns on, tap the icon once and it switches to the microphone.",
  unsureA: "🤔 I could not hear it clearly. Read these lines once more, a bit louder and not too fast.", hearT: "🔊 How the teacher reads it"});
Object.assign(TX.ru, {fixH: "🔁 Повторение", rvH: "🔁 Повторение", rpAbc: "🔤 Алфавит", rpLet: "🧩 Ваши буквы",
  rpEmpty: "Пока пусто. После урока 1 здесь появятся его буквы: бот будет возвращать их через 1, 3, 7 дней и дальше реже — короткими вопросами — так буквы не забываются.",
  rpDemo: "👀 Посмотреть пример повторения", rpDemoNote: "Это пример: как будто вы уже прошли уроки 1–2. Шесть коротких вопросов по буквам.",
  rpGoN: "▶ Повторить сейчас · #", fixDue: "Сегодня пора повторить букв: #. Это шесть коротких вопросов.", fixNone: "Сегодня по плану повторять нечего — можно потренировать пройденные буквы.",
  histEx: "📜 Занятий ещё не было. Вот пример, как будет выглядеть история:", exD1: "вчера", exD2: "2 дня назад",
  hHome: "Нажмите «Начать» или «Продолжить». Уроки, Повторение, Прогресс и Настройки — ниже."});
Object.assign(TX.en, {fixH: "🔁 Review", rvH: "🔁 Review", rpAbc: "🔤 The alphabet", rpLet: "🧩 Your letters",
  rpEmpty: "Empty for now. After lesson 1 its letters appear here: the bot brings them back after 1, 3, 7 days and then less often, with short questions, so they are not forgotten.",
  rpDemo: "👀 See an example review", rpDemoNote: "An example: as if you had done lessons 1–2. Six short questions about the letters.",
  rpGoN: "▶ Review now · #", histEx: "📜 No lessons yet. Here is how the history will look:", exD1: "yesterday", exD2: "2 days ago",
  hHome: "Tap Start or Continue. Lessons, Review, Progress and Settings are below."});
Object.assign(TX.ru, {progEx: "📊 Занятий пока не было. Вот пример, как будет выглядеть прогресс через несколько дней:"});
Object.assign(TX.en, {progEx: "📊 No lessons yet. Here is how your progress will look after a few days:"});
Object.assign(TX.ru, {rpLes: "📖 Пройденные уроки", rpErr: "✏️ Слова с ошибками", rpHalf: "не до конца", rpExL: "Пример:",
  rpLesHint: "Нажмите на урок, чтобы перечитать его и прислать голосовое ещё раз.", rpLesEx: "здесь появятся уроки, которые вы прошли, — любой можно открыть и перечитать.",
  rpErrHint: "Нажмите на слово — откроется урок, где оно есть. Эти слова бот спросит и в повторении.", rpErrEx: "здесь соберутся слова, в которых вы ошиблись; нажмёте — откроется урок с этим словом."});
Object.assign(TX.en, {rpLes: "📖 Lessons done", rpErr: "✏️ Words with mistakes", rpHalf: "not finished", rpExL: "Example:",
  rpLesHint: "Tap a lesson to read it again and send a new voice message.", rpLesEx: "the lessons you have done appear here; open any of them to read again.",
  rpErrHint: "Tap a word to open the lesson where it is. Review asks these words too.", rpErrEx: "words you misread gather here; tap one to open its lesson."});
Object.assign(TX.ru, {rtDue: "Сегодня повторяем: #", rtNone: "Сегодня повторять нечего ✓", rtLater: "Буквы вернутся сами — через 1, 3, 7 дней. Можно потренироваться и сейчас.", rtSub: "6 коротких вопросов · около 2 минут",
  rtGo: "▶ Повторить", rtTrain: "▶ Потренироваться ещё", rtEmpty: "Пока повторять нечего", rtEmptySub: "Пройдите первый урок — его буквы и слова появятся здесь.",
  rtEx: "👀 Пример", rtNo: "пусто · есть пример", rtBack: "‹ Назад", rpLet2: "Мои буквы", rpLes2: "Пройденные уроки", rpErr2: "Слова с ошибками", rpAbc2: "Алфавит",
  ctaA: "👀 Все 28 букв — просто посмотрите. Записывать не нужно.",
  ayT: "▶ Подробный урок", ayBy: "Абу Ясин Руслан Маликов · по-русски", ayMore: "Подробнее · Абу Ясин", xAy: "🎓 Уроки по-русски · Абу Ясин Руслан Маликов (по этой книге)",
  ayL: "Буква #", ayLsub: "урок по книге", ayMk: "Откуда звук #", ayMkSub: "махрадж", ayVsub: "огласовки"});
Object.assign(TX.en, {rtDue: "Today we review: #", rtNone: "Nothing to review today ✓", rtLater: "Letters come back by themselves after 1, 3, 7 days. You can practise now too.", rtSub: "6 short questions · about 2 minutes",
  rtGo: "▶ Review", rtTrain: "▶ Practise more", rtEmpty: "Nothing to review yet", rtEmptySub: "Do the first lesson: its letters and words appear here.",
  rtEx: "👀 Example", rtNo: "empty · see an example", rtBack: "‹ Back", rpLet2: "My letters", rpLes2: "Lessons done", rpErr2: "Words with mistakes", rpAbc2: "The alphabet",
  ctaA: "👀 All 28 letters: just look. Nothing to record.",
  ayT: "▶ Full lesson", ayBy: "Abu Yasin Ruslan Malikov · in Russian", ayMore: "In depth · Abu Yasin", xAy: "🎓 Lessons in Russian · Abu Yasin Ruslan Malikov (same book)",
  ayL: "Letter #", ayLsub: "a lesson by the book", ayMk: "Where # comes from", ayMkSub: "makhraj", ayVsub: "vowel marks"});
/* hints under the phone, in the page's language */
Object.assign(TX.ru, {hStart: "Первое знакомство: язык, затем одно нажатие — согласие. Дальше главный экран с кнопкой «Начать».",
  hLesson: "Посмотрите видео, затем отправьте голосовое: прочитайте слова. Всё остальное — в «📖 Углублённо».", hRule: "Страница правила: пролистайте карточки.",
  hCard: "Карточки меняются на месте. Голос учителя — в видеоуроке; синтезированного звука нет.", hFb: "Сравните «нужно» и «прозвучало», затем переходите к следующей части.",
  hListDemo: "В демо открыты алфавит, уроки 1–15 (все 28 букв) и страницы 49–50; разбор с ошибками — в уроках 1–3.", hMic: "Нажмите 🎤 внизу, когда будете готовы прочитать.",
  hHome: "Нажмите «Начать» или «Продолжить». Уроки, Повторение, Прогресс и Настройки — ниже.", hRev: "Отвечайте: буквы, которые вы знаете, возвращаются всё реже."});
Object.assign(TX.en, {hStart: "First contact: the language, then one tap to agree. Then the home screen with the “Start” button.",
  hLesson: "Watch the video, then send a voice message reading the words. Everything else is under “📖 Go deeper”.", hRule: "A rule page: go through the cards.",
  hCard: "Cards change in place. The teacher's voice is in the video lesson; no synthetic sound.", hFb: "Compare “needed” and “heard”, then go to the next part.",
  hListDemo: "The demo opens the alphabet, lessons 1–15 (all 28 letters) and pages 49–50; feedback with errors is shown in lessons 1–3.", hMic: "Tap 🎤 below when you are ready to read.",
  hHome: "Tap Start or Continue. Lessons, Review, Progress and Settings are below.", hRev: "Answer: letters you know come back less and less often."});
/* ---------- no synthetic or unverified sound: syllables are shown, a real teacher is in the video ---------- */
function ai(h) { return h.replace(/[\u0621-\u064A][\u0621-\u0652\u0670]*/g, function (m) { return '<span class="ai">' + m + "</span>"; }); }
function syl(t) { return '<span class="syl ar">' + esc(t) + "</span>"; }
function vidBtn(T) { return '<div class="rbtn" style="padding:8px 0 0"><button data-a="video">' + T.teachV + "</button></div>"; }

/* ---------- letters remembered: 1 · 3 · 7 · 14 · 30 days ---------- */
var LS = {}, DAY = 0, INT = [0, 1, 3, 7, 14, 30], PART = {}, DONEP = {}, RV = null;
function learn(ch) { if (ch && !LS[ch]) { LS[ch] = {lv: 1, due: DAY + 1}; } }
function weaken(ch) { if (ch) { LS[ch] = {lv: 1, due: DAY + 1}; } }
function strengthen(ch, ok) { var lv = ok ? Math.min(5, (LS[ch] ? LS[ch].lv : 0) + 1) : 1; LS[ch] = {lv: lv, due: DAY + INT[lv]}; }
function isDue(ch) { return !!LS[ch] && LS[ch].due <= DAY; }
function dots(lv) { var d = ""; for (var i = 1; i <= 4; i++) { d += i <= lv ? "●" : "○"; } return d; }
function strText(ch, T) {
  var s = LS[ch]; return f(T.str, !s ? T.strNew : isDue(ch) ? T.strDue : f(T.strIn, s.due - DAY));
}
function chips(list, T) {
  return '<div class="lcs">' + list.map(function (ch) {
    var d = isDue(ch); return '<div class="lc' + (d ? " due" : "") + '"><b class="ar">' + ch + "</b><small>" + (d ? T.today : f(T.inD, LS[ch].due - DAY)) + "</small></div>";
  }).join("") + "</div>";
}
function lessonNo(L) { return typeof L.n === "number" ? L.n : L.page - 9; }
function lname(T, n) { return n === 0 ? T.alphaT : f(T.lesson, n); }
function partLetters(L, p) { var P = L.parts[p]; return (P && P.lt) ? [P.lt] : (LESSON_LETTERS[lessonNo(L)] || "").split(""); }
function lineRange(T, P) { return P.z - P.a === 1 ? f(T.line1, P.a + 1) : f(T.lineN, P.a + 1, P.z); }
function bind(chat, m, name, ctx) { m.querySelectorAll("[data-a]").forEach(function (b) { b.onclick = function () { chat.onReq(name, b.dataset.a, null, ctx, m); }; }); }
function ytCard(T, v) {
  return '<a class="ytc" href="https://www.youtube.com/watch?v=' + v.id + '" target="_blank" rel="noopener"><small>YouTube · ' + esc(v.author || "") + "</small><b>" + esc(v.title) +
    '</b><span><img alt="" src="' + IMG["yt-" + v.id] + '"><i>▶</i><em>' + v.minutes + ":00</em></span></a>";
}

/* ---------- the video: a visible tile that opens exactly this page's fragment ---------- */
function mmss(t) { var p = String(t).split(":"); return (+p[0]) * 60 + (+p[1] || 0); }
function vidUrl(v) {
  return v.from && v.to ? "https://www.youtube.com/embed/" + v.id + "?start=" + mmss(v.from) + "&end=" + mmss(v.to) + "&autoplay=1" : "https://www.youtube.com/watch?v=" + v.id;
}
function vtile(T, v, small, deep) {
  var seg = deep ? T.vShort : v.from && v.to ? f(T.vSeg, v.from, v.to) : f(T.vNoSeg, v.minutes);
  return '<a class="vt' + (small ? " sm" : "") + '" href="' + vidUrl(v) + '" target="_blank" rel="noopener"><span class="th"><img alt="" src="' + IMG["yt-" + v.id] + '"><i>▶</i></span>' +
    "<span><b>" + (deep ? T.vSmall : T.vTitle) + "</b><small>" + esc(v.title) + "</small><em>" + seg + "</em></span></a>";
}
/* only the video that covers this letter (page 12: ت is in video 2, ن in video 3) */
function vidsFor(L, letter) {
  var all = L.videos || [], hit = letter ? all.filter(function (v) { return v.letters && v.letters.indexOf(letter) >= 0; }) : [];
  return hit.length ? hit : all.slice(0, 1);
}
function vtiles(T, L, small, letter) { return vidsFor(L, letter).map(function (v) { return vtile(T, v, small); }).join(""); }

/* ---------- «Посмотрите перед чтением»: урок по книге + как произносится буква ---------- */
function mcard(url, img, badge, title, sub) {
  return '<a class="mc" href="' + url + '" target="_blank" rel="noopener"><span class="mt"><img alt="" src="' + IMG["yt-" + img] + '"><i>▶</i><em>' + badge + "</em></span><b>" + title + "</b><small>" + sub + "</small></a>";
}
function media(T, L, letter, small) {
  var cards = [], pick = function (k) { return letter ? (L.deep || []).filter(function (d) { return d.l === letter && d.k === k; })[0] : null; };
  var ms = pick("ms"), sw = pick("sw"), book = ms ? null : vidsFor(L, letter)[0];
  if (ms) { cards.push(mcard("https://www.youtube.com/watch?v=" + ms.id, ms.id, ms.len || T.mLesson, T.mBook, T.mBookSub)); }
  else if (book) {
    var seg = book.from && book.to;
    cards.push(mcard(vidUrl(book), book.id, seg ? book.from + "–" + book.to : book.minutes + ":00", T.vTitle, (seg ? T.mSeg : f(T.vNoSeg, book.minutes)) + " · " + esc(book.title.replace(/^Уроки таджвида\. /, ""))));
  }
  var ay = ayOf(letter);
  if (ay) { cards.push(mcard("https://www.youtube.com/watch?v=" + ay.id, ay.id, ay.len, T.ayT.replace("▶ ", ""), T.ayBy)); }
  if (sw) {
    cards.push(mcard(sw.long ? "https://www.youtube.com/watch?v=" + sw.id : "https://www.youtube.com/shorts/" + sw.id, sw.id, sw.long ? T.mLesson : "≈2:00",
      f(T.mSw, '<span class="ai">' + letter + "</span>"), sw.long ? T.mSwLong : T.mSwSub));
  }
  if (!cards.length) { return '<div class="vt none">' + T.noVid + "</div>"; }
  return '<div class="media' + (small ? " in" : "") + '"><div class="mh">' + T.mHead + '</div><div class="mg' + (cards.length === 1 ? " one" : "") + '">' + cards.join("") + "</div></div>";
}
/* ---------- the lesson page: page, video, what to read now (any part, any time) ---------- */
function navRow(T, n) {
  var left = n >= 1 ? '<button class="sm" data-a="prev">‹ ' + lname(T, n - 1) + "</button>" : '<button class="sm" data-a="list">' + T.lessons + "</button>";
  return '<div class="rbtn nav3">' + left + '<button class="sm" data-a="home">🏠</button><button class="sm" data-a="next">' + lname(T, n + 1) + " ›</button></div>";
}
/* one video for this part: the short lesson by the book (1–5 min), else the book's long lesson */
function ayOf(letter) { return letter ? DATA.ay.letters["أإء".indexOf(letter) >= 0 ? "ا" : letter] || null : null; }
function vcard(T, L, letter) {
  var ms = letter ? (L.deep || []).filter(function (d) { return d.l === letter && d.k === "ms"; })[0] : null, v = vidsFor(L, letter)[0];
  var ay = L.n === 0 ? DATA.ay.alphabet : ayOf(letter), id, len, title, sub;
  if (L.n === 0) { id = ay.id; len = ay.len; title = T.vcAlpha; sub = T.ayBy; }
  else if (ms) { id = ms.id; len = ms.len || ""; title = T.vcTitle; sub = T.vcSub; }
  else if (ay) { id = ay.id; len = ay.len; title = T.ayT; sub = T.ayBy; }
  else if (v) { id = v.id; len = v.minutes + ":00"; title = T.vTitle; sub = f(T.vNoSeg, v.minutes); }
  else { return ""; }
  var url = v && id === v.id ? vidUrl(v) : "https://www.youtube.com/watch?v=" + id;
  return '<a class="vc" href="' + url + '" target="_blank" rel="noopener"><span class="mt"><img alt="" src="' + IMG["yt-" + id] + '"><i>▶</i>' + (len ? "<em>" + len + "</em>" : "") +
    "</span><span><b>" + title + "</b><small>" + sub + "</small></span></a>" +
    (ms && ay ? '<a class="vc2" href="https://www.youtube.com/watch?v=' + ay.id + '" target="_blank" rel="noopener">🎓 ' + T.ayMore + " · " + ay.len + " ›</a>" : "");
}
/* the part: video, the call to action, the words — big. Nothing else. */
Chat.prototype.readBlock = function (L, p) {
  var T = this.t, P = L.parts[p], N = L.parts.length, done = DONEP[lessonNo(L)] || {}, letter = P.lt || (L.n === 1 ? "ا" : "");
  var tabs = N > 1 ? '<div class="tabs">' + L.parts.map(function (x, j) {
    return '<button class="' + (j === p ? "on" : "") + (done[j] ? " ok" : "") + '" data-a="pt:' + j + '">' + (done[j] ? "✓ " : "") + (j + 1) + (x.lt ? ' · <span class="ar">' + x.lt + "</span>" : "") + "</button>";
  }).join("") + "</div>" : "";
  var words = '<div class="words ar' + (L.n === 0 ? " alpha" : "") + '">' + L.lines.slice(P.a, P.z).map(function (l) { return "<div>" + l.map(function (w) { return "<span>" + esc(w) + "</span>"; }).join(" ") + "</div>"; }).join("") + "</div>";
  if (L.n === 0) {
    var all = [].concat.apply([], L.lines).join("").replace(/\s/g, "").split("");
    words = '<div class="abw ar">' + all.map(function (ch) { return "<span>" + ch + "</span>"; }).join("") + "</div>";
    return '<div class="rdw">' + vcard(T, L, letter) + '<div class="cta">' + T.ctaA + "</div>" + words +
      '<div class="rbtn" style="padding-bottom:0"><button class="go" data-a="next" style="flex:1 1 100%">' + T.alphaGo + "</button></div></div>";
  }
  return '<div class="rdw">' + vcard(T, L, letter) + tabs + '<div class="cta">' + T.cta + "</div>" + words +
    (L.n <= 2 ? '<div class="how">' + T.micHow + "</div>" : "") + "</div>";
};
/* everything else: hidden under «Ещё» */
Chat.prototype.extra = function (L) {
  var T = this.t, self = this, sec = function (title, body) { return '<div class="xs"><b>' + title + "</b>" + body + "</div>"; };
  var sw = (L.deep || []).filter(function (d) { return d.k === "sw"; }).map(function (d) {
    return mcard(d.long ? "https://www.youtube.com/watch?v=" + d.id : "https://www.youtube.com/shorts/" + d.id, d.id, d.long ? T.mLesson : "≈2:00", f(T.mSw, '<span class="ai">' + d.l + "</span>"), d.long ? T.mSwLong : T.mSwSub);
  }).join("");
  var ayc = [];
  if (L.n === 1 || L.n === 2) { DATA.ay.vowels.forEach(function (v) { ayc.push(mcard("https://www.youtube.com/watch?v=" + v.id, v.id, v.len, esc(v.t), T.ayVsub)); }); }
  (L.deep || []).map(function (d) { return d.l; }).filter(function (l, i, a) { return a.indexOf(l) === i; }).forEach(function (l) {
    var y = ayOf(l); if (!y) { return; }
    ayc.push(mcard("https://www.youtube.com/watch?v=" + y.id, y.id, y.len, f(T.ayL, '<span class="ai">' + l + "</span>"), T.ayLsub));
    if (y.mk) { ayc.push(mcard("https://www.youtube.com/watch?v=" + y.mk, y.mk, y.mkl, f(T.ayMk, '<span class="ai">' + l + "</span>"), T.ayMkSub)); }
  });
  var where = (L.where || []).map(function (w) { return '<div style="margin:4px 0"><span class="ai">' + w.l + "</span> " + esc(self.lang === "ru" ? w.ru : w.en) + "</div>"; }).join("");
  return '<details class="xtra"><summary>' + T.extraT + "</summary>" +
    (L.n === 0 ? sec(T.introH, '<div class="cbody hlp">' + T.introHtml + "</div>") : "") +
    sec(T.xPage, '<img class="pg" data-zoom alt="Book page ' + L.page + '" src="' + IMG["page" + L.pageFile] + '">') +
    (ayc.length ? sec(T.xAy, '<div class="mg">' + ayc.join("") + "</div>") : "") +
    (sw ? sec(T.xSw, '<div class="mg">' + sw + "</div>") : "") +
    (L.videos && L.videos.length ? sec(T.dLong, L.videos.map(function (v) { return vtile(T, v, true); }).join("")) : "") +
    (where ? sec(T.dWhere, where) : "") +
    (L.cards[self.lang] && L.cards[self.lang].length ? sec(T.dCards, '<div class="rbtn" style="padding:6px 0 0"><button data-a="learn">' + T.learnL + "</button></div>") : "") + "</details>";
};
Chat.prototype.lesson = function (L, idx) {
  var T = this.t, n = lessonNo(L);
  var head = L.rule ? T.ruleHead : (L.extra ? T.stage2 : lname(T, L.n));
  var body = L.rule ? '<img class="pg" data-zoom alt="Book page ' + L.page + '" src="' + IMG["page" + L.pageFile] + '">' + media(T, L, "") +
      '<div class="st"><span>' + T.ruleHint + '</span></div><div class="rbtn" style="padding-bottom:0"><button class="main" data-a="learn">' + T.ruleBtn + "</button></div>"
    : this.readBlock(L, PART[n] || 0);
  var html = '<div class="rh">' + head + (L.letters ? ' <span class="rl ar">' + L.letters + "</span>" : "") + "</div>" + body + navRow(T, n) + (L.rule ? "" : this.extra(L));
  var m = this.bubble(html, "rich", T.tRich + " · buttons 10.3");
  bind(this, m, "rich", {idx: idx});
  return m;
};
Chat.prototype.part = function (L, p) {
  var T = this.t, n = lessonNo(L);
  var m = this.bubble('<div class="rh">' + (L.extra ? T.stage2 : lname(T, n)) + "</div>" + this.readBlock(L, p) + navRow(T, n), "rich", T.tRich + " · buttons 10.3");
  bind(this, m, "rich", {idx: DATA.lessons.indexOf(L)});
  return m;
};
/* a page that this demo does not fill: still a message with the way around, never a dead end */
Chat.prototype.stub = function (n) {
  var T = this.t, m = this.bubble('<div class="rh">' + f(T.lesson, n, n + 9) + '</div><div class="txt">' + f(T.demoOnly, n + 9) + "</div>" + navRow(T, n), "rich", T.tRich + " · buttons 10.3");
  bind(this, m, "stub", {n: n});
  return m;
};

/* ---------- cards (extra, behind “Go deeper”), edited in place ---------- */
Chat.prototype.card = function (L, i, m, r) {
  var T = this.t, cards = L.cards[this.lang], c = cards[i], N = cards.length, last = i >= N - 1;
  var head = L.rule ? T.ruleHead : (L.extra ? T.stage2 : lname(T, L.n));
  var big = c.a ? '<div class="cbig ar' + (L.rule || L.extra ? " sm" : "") + '">' + esc(typeof c.a === "string" ? c.a : c.a.map(function (x) { return x[0]; }).join("")) + "</div>" : "";
  var body = (c.q ? "" : "<h4>" + esc(c.h) + "</h4>") + big + (c.w ? '<div class="cq"><b>' + T.book + "</b>" + esc(c.w) + "</div>" : "") + (c.e ? '<div class="ce">' + ai(esc(c.e)) + "</div>" : "") +
    (c.s ? '<div class="vbs">' + c.s.map(syl).join("") + "</div>" : "");
  var quiz = c.q ? '<div class="qz">' + ai(esc(c.h)) + '</div><div class="rbtn" style="padding-bottom:4px">' + c.q.map(function (x, k) { return '<button data-a="q:' + k + '">' + esc(x) + "</button>"; }).join("") + "</div>" + (r ? '<div class="cok">' + ai(esc(r)) + "</div>" : "") : "";
  var nav = '<button class="sm" data-a="prev"' + (i ? "" : ' style="visibility:hidden"') + ">" + T.back + '</button><button class="sm" data-a="home">🏠</button>' +
    (!last ? '<button class="sm go" data-a="next">' + T.nextC + "</button>" : '<button class="sm go" data-a="read">' + (L.rule ? T.lessons : T.toRead) + "</button>");
  var html = '<div class="rh">' + head + '<span class="cnt">' + f(T.cardN, i + 1, N) + '</span></div><div class="cdots">' +
    cards.map(function (x, j) { return '<i class="' + (j <= i ? "on" : "") + '"></i>'; }).join("") + '</div><div class="cbody">' + body + "</div>" + quiz +
    media(T, L, c.s ? (/[أإ]/.test(c.s[0].charAt(0)) ? "ا" : c.s[0].charAt(0)) : "", true) + '<div class="rbtn nav3">' + nav + "</div>";
  if (m) { m.innerHTML = html; } else { m = this.bubble(html, "rich", T.tRich + " · " + T.tEdit + " · 10.1"); }
  bind(this, m, "card", {L: L, i: i});
  return m;
};
/* a letter from the home map: exactly that letter */
/* the alphabet after it is done: off the home screen, one tap away */
Chat.prototype.abc = function () {
  var T = this.t, m = this.bubble('<div class="rh">' + T.alphaT + '</div><div class="abg ar">' + DATA.letters.split("").map(function (ch, i) {
    return '<button class="' + (LS[ch] ? (isDue(ch) ? "due" : "ok") : "") + '" data-a="l:' + i + '">' + ch + "</button>"; }).join("") +
    '</div><div class="dim" style="padding:0 12px;font-size:12.5px;text-align:center">' + T.abcHint + '</div><div class="rbtn"><button class="go" data-a="rep">' + T.abcRep +
    '</button><button class="sm" data-a="home">🏠</button></div>', "rich", T.tRich + " · buttons 10.3");
  bind(this, m, "abc", {});
  return m;
};
Chat.prototype.letterCard = function (ch) {
  var T = this.t, lg = this.lang, x = DATA.info[ch], L = DATA.lessons[DATA.byN[x.n]];
  var body = '<div class="cbig ar">' + ch + '</div><div class="vbs">' + x.s.map(syl).join("") + "</div>" +
    (x.q ? '<div class="cq" style="margin-top:8px"><b>' + T.book + "</b>" + esc(x.q[lg]) + "</div>" : "") + (x.e ? '<div class="ce">' + ai(esc(x.e[lg])) + "</div>" : "") +
    (L ? media(T, L, ch, true) : "");
  var m = this.bubble('<div class="rh">' + f(T.letterH, '<span class="ar">' + ch + "</span>", x.n, x.pg) + '</div><div class="cbody">' + body +
    '</div><div class="rbtn"><button class="main" data-a="open">' + f(T.openL, x.n, x.pg) + '</button><button data-a="home" style="flex:0 0 56px">🏠</button></div>', "rich", T.tRich + " · buttons 10.3");
  bind(this, m, "letter", {ch: ch});
  return m;
};

/* ---------- feedback on one part ---------- */
Chat.prototype.feedback = function (L, p, ms) {
  var T = this.t, lg = this.lang, n = lessonNo(L), N = L.parts.length, P = L.parts[p], lines = L.lines.slice(P.a, P.z), total = 0, bad = {};
  ms.forEach(function (x) { bad[x.li + ":" + x.w] = 1; });
  var fl = lines.map(function (l, k) { total += l.length; return "<div>" + l.map(function (w) { return '<span class="' + (bad[(P.a + k) + ":" + w] ? "bad" : "ok") + '">' + esc(w) + "</span>"; }).join(" ") + "</div>"; }).join("");
  var rows = ms.length ? '<div class="fbh">' + T.repeat + "</div>" + ms.map(function (x) {
    var tv = (L.deep || []).filter(function (d) { return d.k === "ms" && d.l === (x.l === "ء" ? "ا" : x.l); })[0];
    return '<div class="fbr"><div>' + ai(esc(x[lg])) + (x.s ? '<div class="cmp"><span><small>' + T.need + '</small><b class="ar">' + x.s + '</b></span><span><small>' + T.heard + '</small><b class="ar">' + x.b + "</b></span></div>" : "") + (tv ? '<a class="hear" href="https://www.youtube.com/watch?v=' + tv.id + '" target="_blank" rel="noopener">' + T.hearT + "</a>" : "") + "</div></div>";
  }).join("") : "";
  var nextLbl = p < N - 1 ? f(T.partNext, p + 2) : (L.extra ? T.lessons : f(T.lessonNext, n + 1));
  var q = '<div class="quote"><b>' + (L.extra ? T.stage2 : lname(T, n)) + (N > 1 ? " · " + f(T.partOf, p + 1, N) : "") + "</b></div>";
  var html = q + '<div class="vd">' + (ms.length ? f(T.vMost, total - ms.length, total) : L.n === 0 ? f(T.vAlpha, total) : f(T.vAll, total)) + '</div><div class="fl ar">' + fl + "</div>" + rows +
    (L.auto ? '<div class="dim" style="font-size:11.5px;padding:4px 12px 0">' + T.autoNote + "</div>" : "") +
    '<div class="rbtn" style="padding-bottom:0"><button data-a="again">' + T.againB + '</button><button class="go" data-a="next">' + nextLbl + "</button></div>" +
    '<div class="rbtn"><button class="sm" data-a="home">' + T.homeB + '</button><button class="sm" data-a="dispute">' + T.botErr + '</button></div><div class="dsp"></div>';
  var m = this.bubble(html, "rich", T.tRich + " · " + T.tQuote);
  bind(this, m, "fb", {L: L, p: p, ms: ms});
  return m;
};

function disputeUI(box, ms, T) {
  function done() { box.innerHTML = T.dThanks; }
  function btns(list, cls) { return '<div class="rbtn">' + list.map(function (x, k) { return '<button class="' + (cls || "") + '" data-d="' + k + '">' + esc(x) + "</button>"; }).join("") + '<button data-d="x">' + T.cancel + "</button></div>"; }
  box.innerHTML = "<b>" + T.dAsk + "</b>" + btns(T.dR);
  box.querySelectorAll("[data-d]").forEach(function (b) {
    b.onclick = function () {
      if (b.dataset.d === "x") { box.innerHTML = ""; return; }
      if (+b.dataset.d < 2 && ms.length) {
        box.innerHTML = "<b>" + T.dWord + "</b>" + btns(ms.map(function (x) { return x.w; }), "arb");
        box.querySelectorAll("[data-d]").forEach(function (w) { w.onclick = function () { if (w.dataset.d === "x") { box.innerHTML = ""; } else { done(); } }; });
      } else { done(); }
    };
  });
}

Chat.prototype.home = function (st) { return this.widget("home", Object.assign({lg: this.lang, t: 28, k: 3, L: DATA.letters}, st), this.t.tWidget + " · 10.4"); };
function partsState(lg) {
  var it = DATA.book.map(function (p) {
    var pg = p.pages, read = pg.filter(function (x) { return ST[x[0]] === "D"; }).length;
    return [p.n - 1, lg === "ru" ? p.ru : p.en, pg[0][1], pg[pg.length - 1][1], read, pg.length];
  });
  it.unshift([0, TX[lg].alphaT, 10, 10, ST[0] === "D" ? 1 : 0, 1]);
  return {lg: lg, v: "parts", it: it};
}
function pagesState(lg, k) {
  var p = DATA.book[k], next = nextLesson();
  return {lg: lg, v: "pages", t: (p.n - 1) + ". " + (lg === "ru" ? p.ru : p.en), it: p.pages.map(function (x) {
    return [x[0], x[1], x[2], ST[x[0]] === "P" ? "C" : ST[x[0]] || (x[3] ? "R" : x[0] === next ? "C" : "N")];
  })};
}
Chat.prototype.list = function () { return this.widget("lessons", partsState(this.lang), this.t.tWidget + " · " + this.t.tUpd + " · 10.4"); };
Chat.prototype.progress = function () {
  var h = homeState(), att = 0, st = 0, ln = 0, du = 0, td = (new Date().getDay() + 6) % 7, wk = "";
  Object.keys(ATT).forEach(function (k) { att += ATT[k]; });
  var lg = this.lang, mn = new Date().toLocaleDateString(lg === "ru" ? "ru-RU" : "en-GB", {month: "long"});
  /* nothing done yet: show an honest example of how it will look */
  if (!att) {
    this.text(this.t.progEx);
    return this.widget("progress", {lg: lg, n: 6, u: 3, vw: 0, k: 3, b: 3, at: 14, wk: [0, 1, 2, 3, 4, 5, 6].map(function (j) { return j <= td && j > td - 3 ? "1" : "0"; }).join(""), td: td, mo: 3, mn: mn}, this.t.tWidget + " · 10.4");
  }
  for (var j = 0; j < 7; j++) { wk += j === td ? "1" : "0"; }
  Object.keys(LS).forEach(function (ch) { if (isDue(ch)) { du++; } else if (LS[ch].lv >= 3) { st++; } else { ln++; } });
  var read = Object.keys(ST).filter(function (k) { return ST[k] === "D"; }).length, viewed = Object.keys(ST).filter(function (k) { return ST[k] === "V"; }).length;
  return this.widget("progress", {lg: this.lang, n: h.n, u: read, vw: viewed, k: h.k, b: h.k, at: att, wk: wk, td: td, mo: 1, mn: mn}, this.t.tWidget + " · 10.4");
};
Chat.prototype.settings = function () { return this.widget("settings", Object.assign({lg: this.lang}, PREF), this.t.tWidget + " · " + this.t.tUpd + " · 10.4"); };

/* ---------- «Закрепить»: questions built from the learner's own letters and mistakes ---------- */
var VOW = ["َ", "ِ", "ُ"];
/* letters that look alike: only the dots tell them apart */
var LOOK = ["بتثني", "جحخ", "دذ", "رز", "سش", "صض", "طظ", "عغ", "فق"];
var DOTS = {
  ru: {ب: "одна точка снизу", ت: "две точки сверху", ث: "три точки сверху", ن: "одна точка сверху", ي: "две точки снизу", ج: "одна точка внутри", ح: "без точек", خ: "одна точка сверху",
    د: "без точек", ذ: "одна точка сверху", ر: "без точек", ز: "одна точка сверху", س: "без точек", ش: "три точки сверху", ص: "без точек", ض: "одна точка сверху",
    ط: "без точек", ظ: "одна точка сверху", ع: "без точек", غ: "одна точка сверху", ف: "одна точка сверху", ق: "две точки сверху"},
  en: {ب: "one dot below", ت: "two dots above", ث: "three dots above", ن: "one dot above", ي: "two dots below", ج: "one dot inside", ح: "no dots", خ: "one dot above",
    د: "no dots", ذ: "one dot above", ر: "no dots", ز: "one dot above", س: "no dots", ش: "three dots above", ص: "no dots", ض: "one dot above",
    ط: "no dots", ظ: "one dot above", ع: "no dots", غ: "one dot above", ف: "one dot above", ق: "two dots above"}
};
/* the same word with another vowel on its first vowelled letter (hamza sits below only with kasra) */
function withVowel(w, v) {
  var i = w.search(/[\u064e\u0650\u064f]/); if (i < 0) { return w; }
  var k = i - 1; while (k > 0 && /[\u064b-\u0652]/.test(w[k])) { k--; }
  var base = w[k]; if (base === "\u0623" || base === "\u0625") { base = v === "\u0650" ? "\u0625" : "\u0623"; }
  return w.slice(0, k) + base + w.slice(k + 1, i) + v + w.slice(i + 1);
}
function lookAlike(ch) { var g = LOOK.filter(function (x) { return x.indexOf(ch) >= 0; })[0]; return g ? g.replace(ch, "").split("").slice(0, 2) : []; }
function buildRound() {
  var learned = Object.keys(LS).filter(function (ch) { return DATA.info[ch]; });
  if (!learned.length) { return null; }
  var due = learned.filter(isDue), pool = due.length ? due : learned, qs = [], k = 0;
  /* 1) the learner's own mistakes first: which syllable was really written? */
  ERR.slice(-2).forEach(function (e) {
    var vi = VOW.indexOf(e.s.slice(-1)), base = e.s.charAt(0); if (vi < 0) { return; }
    var o = VOW.map(function (v) { return withVowel(e.w, v); }), pos = qs.length % 3, right = o.splice(vi, 1)[0];
    o.splice(pos, 0, right);
    qs.push({t: "err", ch: e.l, w: e.w, h: e.h, pg: e.pg, o: o, a: pos, x: e});
  });
  /* 2) then due letters: tell look-alike letters apart, and find a vowel mark */
  while (qs.length < 6 && k < 40) {
    var ch = pool[k % pool.length], x = DATA.info[ch], alike = lookAlike(ch), pos = (k + 1) % 3, vi = (k * 2 + 1) % 3;
    if (k % 2 === 0 && alike.length) { var o = alike.slice(0, 2); while (o.length < 2) { o.push("م"); } o.splice(pos, 0, ch); qs.push({t: "look", ch: ch, o: o, a: pos}); }
    else { qs.push({t: "mark", ch: ch, o: x.s.slice(), a: vi}); }
    k++;
  }
  return {qs: qs.slice(0, 6), i: 0, sc: 0, cb: 0, res: {}, lr: {}, pk: null, end: 0, free: !due.length};
}
Chat.prototype.review = function (m) {
  var T = this.t, lg = this.lang;
  if (!m) { RV = buildRound(); if (!RV) { this.text(T.rvNone); return null; } }
  var q = RV.qs[RV.i], N = RV.qs.length, html;
  var head = '<div class="rh">' + T.rvH + '<span class="cnt">' + (RV.end ? "" : f(T.cardN, RV.i + 1, N) + (RV.cb > 1 ? " · " + f(T.combo, RV.cb) : "")) + "</span></div>" +
    '<div class="cdots">' + RV.qs.map(function (x, j) { return '<i class="' + (RV.res[j] === 1 ? "on" : "") + '"' + (RV.res[j] === 0 ? ' style="background:var(--au)"' : "") + "></i>"; }).join("") + "</div>";
  if (RV.end) {
    html = head + '<div class="cbody"><div class="cbig" style="font:800 40px var(--body);color:var(--g)">' + RV.sc + "/" + N + '</div><h4 style="text-align:center">' + f(T.rvEnd, RV.sc, N) +
      "</h4>" + chips(Object.keys(RV.lr), T) + '</div><div class="rbtn"><button class="sm" data-a="home">🏠</button><button class="go" data-a="again">' + T.rvMore + "</button></div>";
  } else {
    var body = q.t === "err" ? "<h4>" + f(T.rvErr, q.pg) + '</h4><div class="dim cn">' + f(T.rvErr2, '<span class="ai">' + esc(q.h) + "</span>") + "</div>" :
      q.t === "look" ? "<h4>" + f(T.rvLook, '<span class="ar">' + q.ch + "</span>") + "</h4>" :
      "<h4>" + f(T.rvMark, T.vn[q.a]) + "</h4>";
    var ok = RV.pk === q.a, why = "";
    if (RV.pk !== null) {
      why = q.t === "err" ? q.x[lg] : q.t === "look" ? f(T.lookWhy, q.ch, DOTS[lg][q.ch], q.o.filter(function (c) { return c !== q.ch; }).map(function (c) { return c + " — " + DOTS[lg][c]; }).join("; ")) :
        f(T.markWhy, T.vn[q.a], T.shape[q.a], q.o[q.a]);
      why = '<div class="cok">' + (ok ? T.rvOk : T.rvNo) + " " + ai(esc(why)) + "</div>";
    }
    html = head + (RV.free && RV.i === 0 ? '<div class="dim" style="font-size:12px;padding:4px 12px 0">' + T.rvFree + "</div>" : "") + '<div class="cbody">' + body + "</div>" +
      '<div class="rbtn q3" style="padding-bottom:6px">' + q.o.map(function (o, k) {
        return '<button class="arb ' + (RV.pk === null ? "" : k === q.a ? "ok" : k === RV.pk ? "no" : "") + '" data-a="o:' + k + '">' + esc(o) + "</button>";
      }).join("") + "</div>" + why +
      '<div class="rbtn nav3"><button class="sm" data-a="home">🏠</button><span></span>' + (RV.pk !== null ? '<button class="sm go" data-a="next">' + T.rvNext + "</button>" : "<span></span>") + "</div>";
  }
  if (m) { m.innerHTML = html; } else { m = this.bubble(html, "rich", T.tGame + " · " + T.tRich + " · " + T.tEdit); }
  bind(this, m, "rev", {});
  return m;
};
/* «🔁 Повторение»: one clear action on top, four sections one tap away; never an empty screen */
Chat.prototype.fix = function (view, m) {
  var T = this.t, learned = Object.keys(LS).filter(function (ch) { return DATA.info[ch]; }), due = learned.filter(isDue);
  var done = Object.keys(ST).filter(function (k) { return +k > 0 && (ST[k] === "D" || ST[k] === "P"); }).map(Number).sort(function (x, y) { return x - y; });
  var seen = {}, errs = ERR.filter(function (e) { if (seen[e.w]) { return false; } seen[e.w] = 1; return true; });
  var note = function (t, ex) { return '<div class="rnote">' + (ex ? "<i>" + T.rpExL + "</i> " : "") + t + "</div>"; };
  var html, cap = T.tRich + " · buttons 10.3";
  if (!view) {
    var top = learned.length
      ? '<div class="rtop"><b>' + (due.length ? f(T.rtDue, '<span class="ar rta">' + due.join(" ") + "</span>") : T.rtNone) + "</b><small>" + (due.length ? T.rtSub : T.rtLater) + '</small></div><div class="rbtn" style="padding-top:0"><button class="go" data-a="start" style="flex:1 1 100%">' + (due.length ? T.rtGo : T.rtTrain) + "</button></div>"
      : '<div class="rtop"><b>' + T.rtEmpty + "</b><small>" + T.rtEmptySub + '</small></div><div class="rbtn" style="padding-top:0"><button class="go" data-a="next">' + (nextLesson() === 0 ? T.fixGo : "▶ " + lname(T, nextLesson())) + '</button><button data-a="demo">' + T.rtEx + "</button></div>";
    var row = function (v, ic, title, prev, ar, n) {
      return '<button data-a="v:' + v + '"><span class="ic">' + ic + '</span><span class="tx"><b>' + title + "</b><small" + (ar && n ? ' class="ar"' : "") + ">" + (n ? prev : T.rtNo) + '</small></span><span class="ct' + (n ? "" : " z") + '">' + (n || "0") + "</span><i>›</i></button>";
    };
    html = '<div class="rh">' + T.fixH + "</div>" + top + '<div class="rmenu">' +
      row("let", "🧩", T.rpLet2, learned.join(" "), 1, learned.length) +
      row("les", "📖", T.rpLes2, done.map(function (n) { return f(T.lesson, n); }).join(" · "), 0, done.length) +
      row("err", "✏️", T.rpErr2, errs.slice(0, 3).map(function (e) { return esc(e.w); }).join("  "), 1, errs.length) +
      row("abc", "🔤", T.rpAbc2, "ا ب ت ث ج ح خ …", 1, 28) +
      '</div><div class="rbtn"><button data-a="hist">' + T.histB + '</button><button data-a="home">' + T.homeB + "</button></div>";
  } else {
    var title = {let: T.rpLet2, les: T.rpLes2, err: T.rpErr2, abc: T.rpAbc2}[view], body = "";
    if (view === "let") {
      body = learned.length ? chips(learned, T) + note(T.fixRule) + '<div class="rbtn" style="padding:8px 0 0"><button class="go" data-a="start" style="flex:1 1 100%">' + (due.length ? T.rtGo : T.rtTrain) + "</button></div>"
        : note(T.rpEmpty) + '<div class="rbtn" style="padding:8px 0 0"><button data-a="demo" style="flex:1 1 100%">' + T.rpDemo + "</button></div>";
    } else if (view === "les") {
      var ex = !done.length, list = ex ? [1, 2] : done;
      body = '<div class="rl2">' + list.map(function (n) { var L = DATA.lessons[DATA.byN[n]];
        return '<button data-a="o:' + n + '"' + (ex ? " disabled" : "") + "><span>" + f(T.lesson, n) + (ST[n] === "P" ? " · " + T.rpHalf : "") + '</span><b class="ar">' + (L ? L.letters : "") + "</b></button>"; }).join("") + "</div>" + note(ex ? T.rpLesEx : T.rpLesHint, ex);
    } else if (view === "err") {
      var exE = !errs.length, ws = exE ? [DATA.lessons[DATA.byN[1]], DATA.lessons[DATA.byN[2]]].map(function (L) { return {w: L.mistakes[0].w, pg: L.page}; }) : errs;
      body = '<div class="wr ar">' + ws.map(function (e) { return '<button data-a="o:' + (e.pg - 9) + '"' + (exE ? " disabled" : "") + ">" + esc(e.w) + "</button>"; }).join("") + "</div>" + note(exE ? T.rpErrEx : T.rpErrHint, exE);
    } else {
      body = '<div class="abg ar">' + DATA.letters.split("").map(function (ch, i) {
        return '<button class="' + (LS[ch] ? (isDue(ch) ? "due" : "ok") : "") + '" data-a="l:' + i + '">' + ch + "</button>"; }).join("") + "</div>" + note(T.abcHint) +
        '<div class="rbtn" style="padding:8px 0 0"><button data-a="abc" style="flex:1 1 100%">' + T.abcRep + "</button></div>";
    }
    html = '<div class="rh">' + T.fixH + " › " + title + '</div><div class="cbody">' + body + '</div><div class="rbtn"><button data-a="back">' + T.rtBack + '</button><button data-a="home">' + T.homeB + "</button></div>";
  }
  if (m) { m.innerHTML = html; } else { m = this.bubble(html, "rich", cap); }
  bind(this, m, "fix", {});
  return m;
};
Chat.prototype.help = function () {
  var T = this.t, m = this.bubble('<div class="rh">' + T.mHelp + '</div><div class="cbody hlp">' + T.helpHtml + '</div><div class="rbtn"><button class="go" data-a="go">' + T.helpGo +
    '</button><button data-a="home">' + T.homeB + "</button></div>", "rich", T.tRich + " · buttons 10.3");
  bind(this, m, "help", {});
  return m;
};
Chat.prototype.intro = function () {
  var T = this.t, m = this.bubble('<div class="rh">' + T.introH + '</div><div class="cbody hlp">' + T.introHtml + '</div><div class="rbtn" style="padding-bottom:0"><button class="go" data-a="l1" style="flex:1 1 100%">' + T.introGo +
    '</button></div><div class="rbtn"><button data-a="list">' + T.lessons + '</button><button data-a="home">' + T.homeB + "</button></div>", "rich", T.tRich + " · buttons 10.3");
  bind(this, m, "help", {});
  return m;
};
Chat.prototype.more = function () {
  var T = this.t, self = this;
  var m = this.bubble('<div class="rh">' + T.more + '</div><div class="rbtn"><button data-a="help">' + T.mHelp + '</button><button data-a="rem">' + T.mRem + '</button><button data-a="data">' + T.mData + '</button><button data-a="home">' + T.home + "</button></div>", "rich", T.tRich + " · 10.1 + buttons 10.3");
  m.querySelectorAll("[data-a]").forEach(function (b) { b.onclick = function () { self.onReq("more", b.dataset.a, null, null, m); }; });
  return m;
};
Chat.prototype.clear = function () { this.timers.forEach(clearTimeout); this.timers = []; this.box.innerHTML = ""; };

/* ---------------- live simulator ---------------- */
var chatBox = document.getElementById("chat"), mic = document.getElementById("mic"), hint = document.getElementById("hint");
var PL = document.documentElement.getAttribute("data-pl") === "ru" ? "ru" : "en", lang = PL, cur = null, waiting = false, sim, ST = {}, ATT = {}, HIST = [], ERR = [], PREF = {ui: "ru", rem: "19:00", op: 0, big: 0};
var LESSON_LETTERS = {1: "ا"};
DATA.lessons.forEach(function (L) { if (L.n > 1) { LESSON_LETTERS[L.n] = L.letters.replace(/ /g, ""); } });
function pl(en, ru) { return PL === "ru" ? ru : en; }
function nextLesson() { for (var n = 0; n <= 76; n++) { if (ST[n] !== "D" && ST[n] !== "V") { return n; } } return 76; }
function say(h) { hint.textContent = h; }
function setMic(on) { waiting = on; mic.classList.toggle("live", on); }
function homeState() {
  var nl = nextLesson(), c = (nl === 0 ? "ا" : LESSON_LETTERS[nl] || "ي").charAt(0), du = 0, n = 0;
  var m = DATA.letters.split("").map(function (ch) { if (LS[ch]) { n++; if (isDue(ch)) { du++; return "R"; } return "D"; } return ch === c ? "C" : "N"; }).join("");
  var read = Object.keys(ST).filter(function (k) { return ST[k] === "D" && k !== "0"; }).length;
  var nx = DATA.lessons[DATA.byN[nl]], nt = nl > 0 && nx ? nx.letters : "";
  return {n: n, P: read, m: m, nl: nl, nt: nt, a: ST[0] === "D" ? 1 : 0, k: read ? 2 + read : 0, du: du};
}
/* history: an example while there is nothing yet */
function showHistory() {
  if (HIST.length) { sim.widget("history", {lg: lang, e: HIST}, sim.t.tWidget + " · 10.4"); return; }
  sim.text(sim.t.histEx);
  sim.widget("history", {lg: lang, e: [[2, 11, "D", 3, 2, 2, sim.t.exD1, "ر ز م"], [1, 10, "D", 2, 1, 1, sim.t.exD2, "أَ إِ أُ"]]}, sim.t.tWidget + " · 10.4");
}
function goHome() { sim.home(homeState()); say(sim.t.hHome); }
function openLesson(i) { cur = i; sim.lesson(DATA.lessons[i], i); setMic(!DATA.lessons[i].rule); say(DATA.lessons[i].rule ? sim.t.hRule : sim.t.hLesson); }
function openByNumber(n) {
  if (n < 0) { return; }
  var i = DATA.byN[n];
  if (i !== undefined) { openLesson(i); } else { cur = null; sim.stub(n); }
}
function today() { return new Date().toLocaleDateString(lang === "ru" ? "ru-RU" : "en-GB", {day: "numeric", month: "short"}); }

var H = {
  home: function (d) {
    if (d === "go") { openByNumber(nextLesson()); }
    else if (d === "list") { sim.list(); say(sim.t.hListDemo); }
    else if (d === "rev") { sim.fix(); }
    else if (d === "prog") { sim.progress(); }
    else if (d === "set") { sim.settings(); }
    else if (d === "abc") { sim.fix(); }
    else if (d.indexOf("l:") === 0) { sim.letterCard(DATA.letters.charAt(+d.slice(2))); say(sim.t.hCard); }
  },
  rich: function (d, set, ctx, m) {
    var L = DATA.lessons[ctx.idx], T = sim.t, n = lessonNo(L); cur = ctx.idx;
    if (d === "learn") { sim.card(L, 0); say(L.rule ? T.hRule : T.hCard); }
    else if (d.indexOf("pt:") === 0) {
      PART[n] = +d.slice(3); var box = m.querySelector(".rdw"); box.outerHTML = sim.readBlock(L, PART[n]); bind(sim, m, "rich", ctx); setMic(true); say(T.hMic);
    }
    else if (d === "prev") { openByNumber(n - 1); }
    else if (d === "next") {
      if (n === 0) { ST[0] = "D"; }
      if (!ST[n] && !L.rule) { ST[n] = "V"; HIST.unshift([n, L.page, "V", 0, 0, 0, "", L.letters || ""]); }
      if (L.extra) { sim.text(T.nextPage); } else { openByNumber(n + 1); }
    }
    else if (d === "list") { sim.list(); say(T.hListDemo); }
    else if (d === "home") { goHome(); }
  },
  card: function (d, set, ctx, m) {
    var L = ctx.L, T = sim.t, n = lessonNo(L);
    if (d === "next" || d === "prev") { sim.card(L, ctx.i + (d === "next" ? 1 : -1), m); }
    else if (d === "home") { goHome(); }
    else if (d === "list") { sim.list(); }
    else if (d === "read") { if (L.rule) { sim.list(); return; } cur = DATA.lessons.indexOf(L); sim.part(L, PART[n] || 0); setMic(true); say(T.hMic); }
    else if (d.indexOf("q:") === 0) {
      var ok = d === "q:0"; sim.card(L, ctx.i, m, ok ? L.quiz[lang].ok : L.quiz[lang].no);
      if (ok) { ST[n] = "D"; sim.later(function () { sim.text(T.nextPage); }, 900); }
    }
  },
  letter: function (d, set, ctx) {
    if (d === "home") { goHome(); } else if (d === "open") { openByNumber(DATA.info[ctx.ch].n); }
  },
  stub: function (d, set, ctx) {
    if (d === "prev") { openByNumber(ctx.n - 1); } else if (d === "next") { openByNumber(ctx.n + 1); } else if (d === "home") { goHome(); } else if (d === "list") { sim.list(); }
  },
  abc: function (d) {
    if (d === "rep") { openByNumber(0); } else if (d === "home") { goHome(); }
    else if (d.indexOf("l:") === 0) { sim.letterCard(DATA.letters.charAt(+d.slice(2))); say(sim.t.hCard); }
  },
  help: function (d) { if (d === "home") { goHome(); } else if (d === "go") { openByNumber(nextLesson()); } else if (d === "l1") { openByNumber(0); } else if (d === "list") { sim.list(); } },
  fix: function (d, set, ctx, m) {
    if (d === "home") { goHome(); }
    else if (d === "start") { if (sim.review()) { say(sim.t.hRev); } }
    else if (d === "demo") {
      sim.text(sim.t.rpDemoNote);
      ["ا", "ر", "ز", "م"].forEach(function (ch) { if (!LS[ch]) { LS[ch] = {lv: 1, due: DAY}; } });
      if (sim.review()) { say(sim.t.hRev); }
    }
    else if (d === "abc") { openByNumber(0); }
    else if (d.indexOf("o:") === 0) { openByNumber(+d.slice(2)); }
    else if (d.indexOf("l:") === 0) { sim.letterCard(DATA.letters.charAt(+d.slice(2))); say(sim.t.hCard); }
    else if (d === "hist") { showHistory(); }
    else if (d === "back") { sim.fix(null, m); }
    else if (d === "next") { openByNumber(nextLesson()); }
    else if (d.indexOf("v:") === 0) { sim.fix(d.slice(2), m); }
  },
  fb: function (d, set, ctx, m) {
    var L = ctx.L, T = sim.t, n = lessonNo(L), N = L.parts.length;
    if (d === "again") { sim.text(T.again); say(T.hMic); }
    else if (d === "home") { goHome(); }
    else if (d === "dispute") { disputeUI(m.querySelector(".dsp"), ctx.ms, T); }
    else if (d === "next") {
      if (ctx.p < N - 1) { PART[n] = ctx.p + 1; sim.part(L, ctx.p + 1); say(T.hMic); return; }
      if (L.extra) { sim.list(); return; }
      openByNumber(n + 1);
    }
  },
  lessons: function (d, set) {
    if (d === "home") { goHome(); }
    else if (d === "pts") { set(partsState(lang)); }
    else if (d === "pt:0") { openByNumber(0); }
    else if (d.indexOf("pt:") === 0) { set(pagesState(lang, +d.slice(3) - 1)); }
    else if (d.indexOf("o:") === 0) { openByNumber(+d.slice(2)); }
  },
  progress: function (d) {
    if (d === "home") { goHome(); }
    else if (d === "rev") { if (sim.review()) { say(sim.t.hRev); } }
    else if (d === "hist") { showHistory(); }
  },
  history: function (d) { if (d === "home") { goHome(); } else if (d === "prog") { sim.fix(); } else if (d.indexOf("o:") === 0) { openByNumber(+d.slice(2)); } },
  settings: function (d, set) {
    var T = sim.t;
    if (d === "home") { goHome(); return; }
    if (d.indexOf("ui:") === 0) {
      var u = d.slice(3); PREF.ui = u;
      if (u === "kk") { set({ui: "kk"}); sim.text(TX.ru.kk); return; }
      switchLang(u); set({lg: lang, ui: u}); sim.text(sim.t.langSet); return;
    }
    if (d.indexOf("rem:") === 0) { PREF.rem = d.slice(4); set({rem: PREF.rem}); sim.text(PREF.rem === "off" ? T.remOff : f(T.remSet, PREF.rem, homeState().nl, homeState().np)); return; }
    if (d === "op") { PREF.op = PREF.op ? 0 : 1; set({op: PREF.op}); sim.text(PREF.op ? T.opOn : T.opOff); return; }
    if (d === "big") { PREF.big = PREF.big ? 0 : 1; set({big: PREF.big}); if (PREF.big) { sim.text(T.bigSet); } return; }
    if (d === "help") { sim.help(); return; }
    H.more(d);
  },
  rev: function (d, set, ctx, m) {
    if (!RV) { return; }
    var q = RV.qs[RV.i];
    if (d === "home") { goHome(); }
    else if (d === "again") { if (sim.review()) { say(sim.t.hRev); } }
    else if (d.indexOf("o:") === 0) {
      if (RV.pk !== null || RV.end) { return; }
      var k = +d.slice(2), ok = k === q.a; RV.pk = k; RV.res[RV.i] = ok ? 1 : 0;
      if (ok) { RV.sc++; RV.cb++; } else { RV.cb = 0; }
      RV.lr[q.ch] = (RV.lr[q.ch] === undefined ? true : RV.lr[q.ch]) && ok;
      sim.review(m);
    }
    else if (d === "next") {
      RV.i++; RV.pk = null;
      if (RV.i >= RV.qs.length) { RV.i = RV.qs.length - 1; RV.end = 1; Object.keys(RV.lr).forEach(function (ch) { strengthen(ch, RV.lr[ch]); }); }
      sim.review(m);
    }
  },
  more: function (d) {
    var T = sim.t;
    if (d === "home") { goHome(); }
    else if (d === "help") { sim.help(); }
    else if (d === "rem") { sim.text(T.rem); }
    else if (d === "data") { sim.text(T.data); }
  },
  milestone: function (d) { if (d === "st2") { sim.text(sim.t.st2); } },
  onboard: function (d, set, state) {
    if (d.indexOf("lg:") === 0) { switchLang(d === "lg:1" ? "en" : "ru"); set({lg: lang, s: 1}); }
    else if (d === "nm") { set({s: 2}); }
    else if (d === "edit") {
      sim.bubble('<div class="txt">' + (lang === "ru" ? "✏️ Напишите, как к вам обращаться, ответом на это сообщение." : "✏️ Reply to this message with the name to use.") + "</div>", "", "Force reply · 10.3");
      sim.later(function () { sim.bubble('<div class="txt">' + (lang === "ru" ? "Амирхан" : "Amirkhan") + "</div>", "me"); set({nm: lang === "ru" ? "Амирхан" : "Amirkhan", s: 2}); }, 1300);
    }
    else if (d.indexOf("a:") === 0) { var p = d.split(":"), s2 = +p[1], v = Object.assign({}, state.v); v[s2] = +p[2]; set({v: v}); sim.later(function () { set({s: s2 + 1}); }, 350); }
    else if (d === "ok") { set({s: 2}); sim.later(goHome, 500); }
  }
};
var checking = false;
mic.addEventListener("click", function () {
  var T = sim.t;
  if (checking) { return; }
  if (cur === null) { var nx = nextLesson(); cur = DATA.byN[nx] !== undefined ? DATA.byN[nx] : DATA.byN[0]; }
  var L = DATA.lessons[cur], n = lessonNo(L);
  if (L.rule) { sim.voice("0:05", true, false); sim.text(T.noRead); return; }
  if (n === 0) { sim.voice("0:05", true, false); sim.text(T.alphaNoRec); return; }
  var p = PART[n] || 0, P = L.parts[p], nw = 0;
  L.lines.slice(P.a, P.z).forEach(function (l) { nw += l.length; });
  sim.voice("0:" + (10 + nw * 2), true, false);
  if (!document.querySelector(".sim .rich")) { sim.text(f(T.guess, n, L.page)); }
  var draft = sim.bubble('<div class="txt"><div>' + T.d1 + '</div></div><button class="stop">' + T.stop + "</button>", "draft", T.tDraft + " · 10.1–10.3");
  var txt = draft.querySelector(".txt"), stopped = false;
  checking = true;
  draft.querySelector(".stop").onclick = function () { stopped = true; checking = false; this.remove(); txt.innerHTML = "<div>" + T.stopped + "</div>"; say(T.hMic); };
  sim.later(function () { if (!stopped) { txt.insertAdjacentHTML("beforeend", "<div>" + f(T.d2, nw, L.page) + "</div>"); } }, 700);
  sim.later(function () { if (!stopped) { txt.insertAdjacentHTML("beforeend", "<div>" + T.d3 + "</div>"); } }, 1400);
  sim.later(function () {
    if (stopped) { return; }
    checking = false;
    if (draft.previousSibling && draft.previousSibling.className === "tag") { draft.previousSibling.remove(); }
    draft.remove();
    if (n === 2 && p === 1 && !ATT[n + ":" + p + "u"]) { ATT[n + ":" + p + "u"] = 1; sim.text(T.unsureA); say(T.hMic); return; }
    var key = n + ":" + p, first = !ATT[key]; ATT[key] = (ATT[key] || 0) + 1;
    var ms = first ? L.mistakes.filter(function (x) { return x.li >= P.a && x.li < P.z; }) : [];
    partLetters(L, p).forEach(learn);
    ms.forEach(function (x) { ERR.push({w: x.w, h: x.h, b: x.b, pg: L.page, l: x.l, s: x.s, ru: x.ru, en: x.en}); weaken(x.l); });
    DONEP[n] = DONEP[n] || {}; DONEP[n][p] = 1;
    var all = L.parts.every(function (x, j) { return DONEP[n][j]; });
    ST[n] = all ? "D" : "P";
    var h = HIST.filter(function (e) { return e[0] === n; })[0];
    if (!h) { h = [n, L.page, ST[n], 0, 0, 0, today(), L.letters || ""]; HIST.unshift(h); }
    h[2] = ST[n]; h[3] += 1; h[4] += ms.length; h[6] = today(); if (!first) { h[5] = h[4]; }
    sim.feedback(L, p, ms); say(T.hFb);
  }, 2200);
});
function switchLang(l) {
  lang = l; sim.t = TX[l]; sim.lang = l; PREF.ui = l;
  document.querySelectorAll("#lang button[data-l]").forEach(function (x) { x.classList.toggle("on", x.dataset.l === l); });
  document.getElementById("ph").textContent = sim.t.ph; document.getElementById("status").textContent = sim.t.status;
}
function restart() {
  if (sim) { sim.clear(); }
  sim = new Chat(chatBox, TX[lang], lang, {live: true, onReq: function (name, d, set, state, m) { if (H[name]) { H[name](d, set, state, m); } }});
  setMic(true); checking = false; cur = null; ST = {}; ATT = {}; HIST = []; ERR = []; LS = {}; DAY = 0; PART = {}; DONEP = {}; RV = null; PREF.ui = lang;
  document.getElementById("ph").textContent = sim.t.ph; document.getElementById("status").textContent = sim.t.status;
  document.querySelectorAll("#lang button[data-l]").forEach(function (x) { x.classList.toggle("on", x.dataset.l === lang); });
  sim.widget("onboard", {lg: lang, s: 0, nm: lang === "ru" ? "Амир" : "Amir", v: {}}, sim.t.tWidget + " · " + sim.t.tUpd + " · 10.4");
  say(sim.t.hStart);
}
document.getElementById("restart").onclick = restart;
document.getElementById("j49").onclick = function () { openLesson(DATA.idx49); };
document.getElementById("j50").onclick = function () { openLesson(DATA.idx50); };
document.getElementById("jms").onclick = function () { sim.widget("milestone", {lg: lang, t: 28, u: 15, k: 21, s2: 1}, sim.t.tWidget + " · 10.4"); say(""); };
document.getElementById("jday").onclick = function () { DAY += 1; sim.text(sim.t.dayP); goHome(); };
document.getElementById("lang").addEventListener("click", function (e) {
  var b = e.target.closest("button[data-l]"); if (!b) { return; }
  lang = b.dataset.l; this.querySelectorAll("button[data-l]").forEach(function (x) { x.classList.toggle("on", x === b); }); restart();
});
restart();

/* ---------------- static gallery (follows the page language) ---------------- */
function buildGallery() {
  var L = DATA.lessons[DATA.byN[2]], gal = document.getElementById("gal"), T = TX[PL], W = T.tWidget + " · " + T.tUpd + " · 10.4";
  gal.innerHTML = "";
  function phone(title, note, fill) {
    var fig = document.createElement("figure");
    fig.innerHTML = '<div class="phone"><div class="top"><div class="ava">م</div><div><div class="nm">Muallim</div><div class="sb">' + T.status + '</div></div></div><div class="chat"></div></div><figcaption><b>' + title + "</b><span>" + note + "</span></figcaption>";
    gal.appendChild(fig); fill(new Chat(fig.querySelector(".chat"), T, PL, {live: false}));
  }
  var keep = {LS: LS, ST: ST, DONEP: DONEP, PART: PART, RV: RV, ERR: ERR, ATT: ATT};
  LS = {"ا": {lv: 2, due: 3}, "ر": {lv: 1, due: 0}}; ST = {1: "D", 2: "P"}; DONEP = {2: {0: 1}}; PART = {2: 1}; ERR = []; ATT = {};
  var A0 = DATA.lessons[DATA.byN[0]];
  phone(pl("1 · First contact", "1 · Первое знакомство"), pl("Two taps: the language, then “I agree” to keeping the recordings. No questions: whoever comes is a beginner.", "Два нажатия: язык, затем «Согласен(на)» на хранение записей. Никаких вопросов: кто пришёл — тот новичок."), function (c) { c.widget("onboard", {lg: PL, s: 0, v: {}}, W); });
  phone(pl("2 · Home, first visit", "2 · Главный экран, первый раз"), pl("The 28 letters, and under them one big button: “Start” (the alphabet first). Below: Lessons, Review, Progress, Settings.", "28 букв и под ними одна большая кнопка «Начать» (сначала алфавит). Ниже: Уроки, Повторение, Прогресс, Настройки."), function (c) { c.home({n: 0, P: 0, m: DATA.start.m, nl: 0, a: 0, k: 0, du: 0}); });
  phone(pl("3 · The alphabet", "3 · Алфавит"), pl("All 28 letters in large type, with Abu Yasin's 5-minute video lesson on the alphabet. Nothing to record; one button to lesson 1.", "Все 28 букв крупно и пятиминутный видеоурок Абу Ясина об алфавите. Записывать не нужно; одна кнопка — к уроку 1."), function (c) { c.lesson(A0, DATA.byN[0]); });
  phone(pl("4 · Home, coming back", "4 · Главный экран, возвращение"), pl("No letter table any more: progress, then “Continue: lesson N” with its letters. The alphabet is now inside 🔁 Review.", "Таблицы букв больше нет: прогресс, затем «Продолжить: урок N» с его буквами. Алфавит теперь внутри «🔁 Повторение»."), function (c) { c.home(Object.assign(homeState(), {a: 1})); });
  phone(pl("5 · The lesson", "5 · Урок"), pl("A short video by the book, a link to the full Russian lesson, the call to record, the words in large type, how to hold the microphone (lessons 1–2), ‹ 🏠 ›. Everything else under “Go deeper”.", "Короткое видео по книге, ссылка на полный урок по-русски, призыв записать, крупные слова, как держать микрофон (уроки 1–2), ‹ 🏠 ›. Всё остальное — в «Углублённо»."), function (c) { c.lesson(L, DATA.byN[2]); });
  phone(pl("6 · Feedback", "6 · Разбор"), pl("Every word green or gold; for the gold one: what was needed and what was heard, how the mouth moves, and 🔊 the teacher's lesson for that letter.", "Каждое слово зелёное или жёлтое; для жёлтого — что нужно и что прозвучало, как двигаются губы и 🔊 урок учителя по этой букве."), function (c) { c.feedback(L, 1, L.mistakes.filter(function (x) { return x.li >= 1 && x.li < 3; })); });
  phone(pl("7 · Not sure", "7 · Не уверен"), pl("When the check is not confident, the bot does not guess: it asks to read once more.", "Когда проверка не уверена, бот не гадает, а просит прочитать ещё раз."), function (c) { c.voice("0:18", true, false); c.text(T.unsureA); });
  phone(pl("8 · 🔁 Review", "8 · 🔁 Повторение"), pl("One clear action on top (what to review today, or start lesson 1), then four sections one tap away: my letters, lessons done, words with mistakes, the alphabet. Empty ones show an example.", "Сверху одно понятное действие (что повторить сегодня или начать урок 1), ниже четыре раздела в одно нажатие: мои буквы, пройденные уроки, слова с ошибками, алфавит. Пустые показывают пример."), function (c) { c.fix(); });
  phone(pl("9 · A review round", "9 · Раунд повторения"), pl("Six quick questions from the learner's own letters and mistakes: a misread word as the book writes it, look-alike letters (the dots), which syllable has a vowel mark.", "Шесть быстрых вопросов по своим буквам и ошибкам ученика: слово с ошибкой — как оно написано в книге, похожие буквы (точки), на каком слоге огласовка."), function (c) {
    ERR = [{w: "زِرْ", h: "زَرْ", pg: 11, l: "ز", s: "زِ", ru: L.mistakes[0].ru, en: L.mistakes[0].en}]; LS["ز"] = {lv: 1, due: 0};
    var m = c.review(); var q = RV.qs[0]; RV.pk = q.a; RV.res[0] = 1; RV.sc = 1; RV.cb = 1; RV.lr[q.ch] = true; c.review(m); ERR = [];
  });
  phone(pl("10 · A letter card", "10 · Карточка буквы"), pl("From the letter table: the letter, its three syllables, the book's words and the video lessons. No synthetic sound.", "Из таблицы букв: буква, три её слога, слова книги и видеоуроки. Без синтезированного звука."), function (c) { c.letterCard("ز"); });
  phone(pl("11 · All lessons", "11 · Все уроки"), pl("The alphabet, then the book's parts 1–8. Everything is open.", "Алфавит, затем части книги 1–8. Всё открыто."), function (c) { c.list(); });
  phone(pl("12 · Lessons of a part", "12 · Уроки части"), pl("Part 1: lessons 1–15, all 28 letters. ✅ read · 🟡 started · 👁 viewed.", "Часть 1: уроки 1–15, все 28 букв. ✅ прочитан · 🟡 начат · 👁 открыт."), function (c) { c.widget("lessons", pagesState(PL, 0), W); });
  phone(pl("13 · Progress", "13 · Прогресс"), pl("Letters out of 28 and lessons out of 15, the streak, the study days Mo–Su with ✓, days this week and this month, and the history.", "Буквы из 28 и уроки из 15, серия, дни занятий Пн–Вс с ✓, дни за неделю и месяц, и история."), function (c) { ATT = {"1:0": 1, "2:0": 1}; c.progress(); ATT = {}; });
  phone(pl("14 · History", "14 · История"), pl("Opened from Review or Progress. Each lesson: date, attempts, errors found and fixed.", "Открывается из Повторения или Прогресса. По каждому уроку: дата, попытки, найденные и исправленные ошибки."), function (c) { c.widget("history", {lg: PL, e: [[2, 11, "P", 1, 1, 0, pl("14 Nov", "14 ноя"), "ر ز م"], [1, 10, "D", 1, 1, 0, pl("13 Nov", "13 ноя"), "أَ إِ أُ"]]}, T.tWidget + " · 10.4"); });
  phone(pl("15 · Settings", "15 · Настройки"), pl("Language, reminder, isti'adha, larger letters, and “How to study”.", "Язык, напоминание, истиаза, крупные буквы и «Как заниматься»."), function (c) { c.settings(); });
  phone(pl("16 · A rule page (Stage II)", "16 · Страница правила (Этап II)"), pl("The book's words, the example highlighted, and one question.", "Слова книги, выделенный пример и один вопрос."), function (c) { c.card(DATA.lessons[DATA.idx50], 3); });
  LS = keep.LS; ST = keep.ST; DONEP = keep.DONEP; PART = keep.PART; RV = keep.RV; ERR = keep.ERR; ATT = keep.ATT;
}
buildGallery();

/* ---------------- lesson plans (follow the page language) ---------------- */
function buildPlans() {
  var box = document.getElementById("lessonCards"); box.innerHTML = "";
  DATA.lessons.forEach(function (L, idx) {
    if (L.auto) { return; }
    var vids = (L.videos || []).map(function (v) { return esc(v.title) + " · " + v.minutes + pl(" min", " мин"); }).join("<br>");
    var chips = (L.cards[PL] || L.cards.en).map(function (c) { return "<u>" + esc(c.h) + "</u>"; }).join("");
    var deep = (L.deep || []).filter(function (d) { return d.k === "sw"; }).map(function (d) { return d.l + pl(" · Dr. Ayman Swaid", " · д-р Айман Сувейд"); }).join("<br>");
    var parts = L.parts.map(function (P, j) {
      return '<div class="dim" style="font-size:12px;margin-top:4px">' + pl("Part ", "Часть ") + (j + 1) + (P.lt ? " · " + P.lt : "") + " · " + (P.z - P.a === 1 ? pl("line ", "строка ") + (P.a + 1) : pl("lines ", "строки ") + (P.a + 1) + "–" + P.z) + '</div><span class="lines">' +
        L.lines.slice(P.a, P.z).map(function (l) { return esc(l.join(" ")); }).join("<br>") + "</span>";
    }).join("");
    function step(icon, title, body, tag) { return "<li><i>" + icon + "</i><div><b>" + title + "</b><span>" + body + "</span><em>" + tag + "</em></div></li>"; }
    var steps = step("📄", pl("The lesson", "Урок"), L.rule ? pl("A rule page of the book, shown whole.", "Страница правила из книги, целиком.") : pl("The short video by the book, the words to read in large type, and “Go deeper” with the book page and more videos.", "Короткое видео по книге, крупные слова для чтения и «Углублённо» со страницей книги и другими видео."), pl("Rich message · link preview · buttons", "Расширенное сообщение · превью ссылки · кнопки")) +
      step("▶️", pl("Video lesson", "Видеоурок"), vids ? '<button class="pill" style="margin-top:3px" data-vids="' + idx + '">' + vids + "</button>" : pl("Short video to be chosen or recorded", "Короткое видео — выбрать или записать"), pl("Link preview → YouTube", "Превью ссылки → YouTube")) +
      step("🃏", L.rule ? pl("The rule, card by card", "Правило, карточка за карточкой") : pl("Learn, card by card", "Учить, карточка за карточкой"), '<span class="chips">' + chips + "</span>", pl("Rich message · voice blocks · edited in place", "Расширенное сообщение · голосовые блоки · правка на месте")) +
      (L.lines.length ? step("🎤", pl("Read aloud, part by part", "Чтение вслух, по частям"), parts, pl("Voice message → feedback per part", "Голосовое → разбор по каждой части")) +
        step("💬", pl("Feedback", "Разбор"), pl("Every word green or gold; for each gold word a plain sentence and the teacher's lesson; then again or the next part.", "Каждое слово зелёное или жёлтое; к жёлтому — простое предложение и урок учителя; затем ещё раз или следующая часть."), pl("Live draft · rich message · voice blocks", "Живой черновик · расширенное сообщение · голосовые блоки")) : "") +
      (deep ? step("🗣", pl("How each letter is pronounced", "Как произносится каждая буква"), deep, pl("Under “Go deeper”", "В «Углублённо»")) : "");
    var c = document.createElement("article"); c.className = "plan";
    c.innerHTML = '<header><div><span class="' + (L.rule ? "rule" : "") + '">' + esc(PL === "ru" && L.labelRu ? L.labelRu : L.label) + "</span><h3>" + esc(PL === "ru" && L.titleRu ? L.titleRu : L.titleEn) + "</h3></div>" + (L.letters ? '<div class="ltr">' + L.letters + "</div>" : "") + "</header>" +
      '<div class="bd"><img data-zoom alt="Book page ' + L.page + '" src="' + IMG["page" + L.pageFile] + '"><ol>' + steps + "</ol></div>" +
      '<footer><button data-show="' + idx + '">' + pl("▶ Open in the phone", "▶ Открыть в телефоне") + "</button></footer>";
    box.appendChild(c);
  });
}
buildPlans();

document.getElementById("lessonCards").addEventListener("click", function (e) {
  var b = e.target.closest("[data-show]"); if (!b) { return; }
  document.querySelector(".sim").scrollIntoView({behavior: "smooth", block: "start"});
  openLesson(+b.dataset.show);
});


/* home example in the page */
function buildHomeShot() { var box = document.getElementById("homeShot"); box.innerHTML = ""; var c = new Chat(box, TX[PL], PL, {live: false}); c.home({n: 6, P: 3, a: 1, m: DATA.after.m, nl: 4, nt: "ي ب", k: 5}); }
buildHomeShot();

/* ---------------- teacher annotation demo ---------------- */
var FATHA = "\u064e", KASRA = "\u0650", DAMMA = "\u064f", SUKUN = "\u0652", SHADDA = "\u0651";
var CONF = {"ر": ["ل", "غ", "ز"], "ز": ["ذ", "س", "ظ"], "م": ["ن", "ب"], "ت": ["ط", "د", "ث"], "ن": ["م", "ل"], "أ": ["ع", "ه"], "إ": ["ع", "ه"], "ا": ["ع", "ه"]};
function baseOf(cell) { return cell.charAt(0); }
function marksOf(cell) { return cell.slice(1); }
function seat(base, v) { if (base === "أ" || base === "إ") { return v === KASRA ? "إ" : "أ"; } return base; }
/* пять форм буквы: с фатхой, кясрой, даммой, сукуном и шаддой — кроме той, что написана */
function forms(cell) {
  var b = baseOf(cell), v = (cell.match(/[\u064e\u0650\u064f]/) || [FATHA])[0];
  var all = [seat(b, FATHA) + FATHA, seat(b, KASRA) + KASRA, seat(b, DAMMA) + DAMMA, seat(b, FATHA) + SUKUN, b + SHADDA + v];
  return all.filter(function (x) { return x !== cell; });
}
function ruleOf(cell, heard) {
  if (heard.indexOf(SHADDA) >= 0 || cell.indexOf(SHADDA) >= 0) { return {ru: "Шадда", en: "Shadda"}; }
  if (heard.indexOf(SUKUN) >= 0 || cell.indexOf(SUKUN) >= 0) { return {ru: "Сукун", en: "Sukun"}; }
  return {ru: "Огласовка", en: "Vowel"};
}
var KIND = {
  en: {letter: "Letter", vowel: "Vowel", sukun: "Sukun", shadda: "Shadda", madd: "Length", missing: "Missing", extra: "Extra sound", tafkhim: "Heaviness", ghunna: "Ghunna", qalqala: "Qalqala", halting: "Hesitated", wrong_stop: "Wrong stop"},
  ru: {letter: "Буква", vowel: "Огласовка", sukun: "Сукун", shadda: "Шадда", madd: "Длина", missing: "Пропуск", extra: "Лишний звук", tafkhim: "Твёрдость", ghunna: "Гунна", qalqala: "Калькаля", halting: "Запнулся", wrong_stop: "Не там остановился"}
};
var TT = {
  en: {rec: "Learner's recording · page # · line #", saved: "Saved: #", right: "the model is right", clean: "clean", skip: "skipped",
    sum: "the model found and you confirmed: # · the model was wrong: # · you added (the model missed): #",
    cant: "cannot be told (#), sent for a second review", line: "line # · 0:07", slow: "line # · slowed to 0.75× · 0:09",
    noteAsk: "💬 Write your comment as a reply to this message.", noteDemo: "Reads the right letter but stretches the vowel too long.",
    noteOk: "Comment saved for recording #.", undo: "↩️ Last action undone.", prevNo: "This is the first recording.",
    reasons: {noise: "poor audio", quiet: "too quiet", ambiguous: "ambiguous", second: "needs a 2nd review"}, sure: "🤖 #% · the model hears it as correct"},
  ru: {rec: "Запись ученика · стр. # · строка #", saved: "Сохранено: #", right: "бот прав", clean: "чисто", skip: "пропущено",
    sum: "бот нашёл, вы подтвердили: # · бот ошибся: # · добавили вы (бот пропустил): #",
    cant: "нельзя определить (#), запись ушла на вторую проверку", line: "строка # · 0:07", slow: "строка # · медленно 0.75× · 0:09",
    noteAsk: "💬 Напишите комментарий ответом на это сообщение.", noteDemo: "Букву читает верно, но слишком растягивает огласовку.",
    noteOk: "Комментарий к записи # сохранён.", undo: "↩️ Последнее действие отменено.", prevNo: "Это первая запись.",
    reasons: {noise: "плохое качество", quiet: "слишком тихо", ambiguous: "неоднозначно", second: "нужна вторая проверка"}, sure: "🤖 #% · бот слышит верно"}
};
var teach, STACK = [], SAVED = [];
function teachTask(q, lg) {
  var t = DATA.annot[q], keep = SAVED[q];
  return {lg: lg, q: q, Q: DATA.annot.length, pg: t.pg, li: t.li, c: t.c, cf: t.cf, bv: t.bv[lg], mk: keep ? keep.mk : {},
    sel: null, fm: [], al: [], vw: 0, more: 0, un: 0, ed: keep ? 1 : 0, end: 0, sd: ""};
}
function teacherStart() {
  var box = document.getElementById("teachChat"); if (!box) { return; }
  if (teach) { teach.clear(); }
  STACK = []; SAVED = [];
  var lg = lang, T = TT[lg];
  function detail(st, i) {
    var d = DATA.annot[st.q].det[i];
    return d ? "🤖 " + d[0] + "% · " + (lg === "ru" ? d[1] : d[2]) : f(T.sure, 95 + (i % 4));
  }
  function src(st, i) { return st.cf.charAt(i) === "g" ? "t" : "a"; }
  teach = new Chat(box, TX[lg], lg, {live: true, onReq: function (name, d, set, st) {
    function change(patch) { STACK.push(JSON.stringify(st)); set(patch); }
    function next(word) {
      SAVED[st.q] = {mk: st.mk};
      teach.eph(f(T.saved, word));
      var q = st.q + 1;
      if (q >= DATA.annot.length) { change({end: 1}); return; }
      teach.voice("0:0" + (6 + q) + " · " + f(T.rec, DATA.annot[q].pg, DATA.annot[q].li), false, false);
      change(teachTask(q, lg));
    }
    function summary() {
      var found = 0, wrong = 0, added = 0;
      for (var i = 0; i < st.cf.length; i++) {
        var m = st.mk[i], flagged = st.cf.charAt(i) === "r";
        if (m && m[1] === "a") { found++; } else if (m && m[1] === "t") { added++; } else if (flagged) { wrong++; }
      }
      return f(T.sum, found, wrong, added);
    }
    if (d === "right") { next(T.right); }
    else if (d === "clean") { next(T.clean); }
    else if (d === "skip") { next(T.skip); }
    else if (d === "done") { next(summary()); }
    else if (d === "line") { teach.voice(f(T.line, st.li), false, true); }
    else if (d === "slow") { teach.voice(f(T.slow, st.li), false, true); }
    else if (d === "cant") { change({un: 1, sel: null}); }
    else if (d.indexOf("u:") === 0) { next(f(T.cant, T.reasons[d.slice(2)])); }
    else if (d === "note") {
      teach.bubble('<div class="txt">' + T.noteAsk + "</div>", "", "Force reply · 10.3");
      teach.later(function () { teach.bubble('<div class="txt">' + T.noteDemo + "</div>", "me"); teach.later(function () { teach.eph(f(T.noteOk, st.q + 1)); }, 500); }, 1200);
    }
    else if (d === "undo") { if (STACK.length) { set(JSON.parse(STACK.pop())); teach.eph(T.undo); } }
    else if (d === "prev") { if (st.q > 0 || st.end) { change(teachTask(st.end ? st.q : st.q - 1, lg)); } else { teach.eph(T.prevNo); } }
    else if (d.indexOf("c:") === 0) {
      var i = +d.slice(2), mk = Object.assign({}, st.mk);
      if (mk[i]) { delete mk[i]; change({mk: mk, sel: null, ed: 1, sd: ""}); } else { change({sel: i, fm: forms(st.c[i]), vw: 0, more: 0, un: 0, ed: 1, sd: detail(st, i)}); }
    }
    else if (d === "more") { change({more: 1}); }
    else if (d === "oth") { change({vw: 1, al: (CONF[baseOf(st.c[st.sel])] || ["ع", "ه", "ح"]).map(function (x) { return x + marksOf(st.c[st.sel]); })}); }
    else if (d.indexOf("h:") === 0) { var hf = st.fm[+d.slice(2)], m1 = Object.assign({}, st.mk); m1[st.sel] = [ruleOf(st.c[st.sel], hf)[lg] + " → " + hf, src(st, st.sel)]; change({mk: m1, sel: null, sd: ""}); }
    else if (d.indexOf("a:") === 0) { var al = st.al[+d.slice(2)], m2 = Object.assign({}, st.mk); m2[st.sel] = [KIND[lg].letter + " → " + al, src(st, st.sel)]; change({mk: m2, sel: null, vw: 0, sd: ""}); }
    else if (d.indexOf("k:") === 0) { var m3 = Object.assign({}, st.mk); m3[st.sel] = [KIND[lg][d.slice(2)], src(st, st.sel)]; change({mk: m3, sel: null, more: 0, sd: ""}); }
  }});
  teach.voice("0:06 · " + f(T.rec, DATA.annot[0].pg, DATA.annot[0].li), false, false);
  teach.widget("annotate", teachTask(0, lg), TX[lg].tWidget + " · " + TX[lg].tUpd + " · 10.4");
}
teacherStart();
var _restart = restart;
restart = function () { _restart(); teacherStart(); };
/* RU / EN at the top: the whole page, the phone, the gallery, the plans and the hints */
document.getElementById("plang").addEventListener("click", function (e) {
  var b = e.target.closest("button[data-pl]"); if (!b || b.dataset.pl === PL) { return; }
  PL = b.dataset.pl; document.documentElement.setAttribute("data-pl", PL);
  try { localStorage.setItem("muallim-pl", PL); } catch (err) {}
  document.documentElement.lang = PL;
  buildGallery(); buildPlans(); buildHomeShot();
  lang = PL; document.querySelectorAll("#lang button[data-l]").forEach(function (x) { x.classList.toggle("on", x.dataset.l === PL); });
  restart();
});
document.documentElement.lang = PL;
document.getElementById("restart").onclick = restart;
