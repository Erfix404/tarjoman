# ترجمان

<div dir="rtl">

**ترجمان یک مهارت (skill) برای ایجنت‌های هوش مصنوعی است که آن‌ها را مترجم و ویراستار حرفه‌ای فارسی می‌کند.**

ترجمان خودش مترجم ماشینی نیست. ترجمه را ایجنت (مثلاً Claude) انجام می‌دهد؛ ترجمان به او یاد می‌دهد **چطور** ترجمه کند: کدام راهنمای سبک را بخواند، پیش‌نویس را چطور از نو بنویسد تا «ترجمه‌ای» به نظر نیاید، و با چه ابزارهایی کارش را بررسی کند.

- سبک‌ها: محاوره و چت، رمان، ژانرهای داستانی (ترسناک، طنز، کودک، شعر، معمایی و جنایی، علمی‌تخیلی و فانتزی)، خاطرات و زندگی‌نامه، نمایشنامه و فیلمنامه، کمیک، بازی، زیرنویس و دوبله، فنی و رابط کاربری، علمی، پزشکی، حقوقی، خبر، مالی، فلسفه، متن کهن، تبلیغات
- حالت ویراستار و فارسی‌به-فارسی: روان کردن متن ماشینی (`editor.md` + `editor-najafi.md`)، روان‌سازی با حفظ سطح (`naturalize.md`) و خودمونی‌سازی (`colloquialize.md`)، همراه با پروتکل وفاداری خزاعی‌فر (`fidelity.md`)
- کتاب: واژه‌نامه، فهرست شخصیت‌ها، شیوه‌نامه و بررسی یکدستی فصل‌ها
- ابزارها: اصلاح خودکار امن نگارش (`fix`)، لینتر سبک‌محور با خروجی `--json` و تفکیک شدت (`lint`)، بررسی کامل بودن ترجمه (`verify`)، بررسی زیرنویس (`srt check`)

---

## نصب

### Claude Code

مهارت را در پوشه‌ی مهارت‌های Claude Code کپی کن.

برای همه‌ی پروژه‌هایت:

```bash
git clone https://github.com/Erfix404/tarjoman.git
mkdir -p ~/.claude/skills
cp -r tarjoman/.claude/skills/tarjoman ~/.claude/skills/
```

فقط برای یک پروژه:

```bash
mkdir -p your-project/.claude/skills
cp -r tarjoman/.claude/skills/tarjoman your-project/.claude/skills/
```

بعد ابزارهای بررسی را نصب کن (پایتون ۳.۱۰ یا بالاتر):

```bash
pip install git+https://github.com/Erfix404/tarjoman.git
tarjoman --help
```

بدون این مرحله هم مهارت کار می‌کند، ولی لینتر در «حالت محدود» اجرا می‌شود و غلط املایی، نیم‌فاصله‌ی محاوره و نشانه‌های متن ماشینی را نمی‌گیرد.

### Claude.ai و Claude Desktop

پوشه‌ی `.claude/skills/tarjoman` را zip کن و در تنظیمات Claude، بخش Skills، بارگذاری کن. ابزارهای پایتونی در این حالت در دسترس نیستند، ولی راهنماها کار می‌کنند.

### ایجنت‌های دیگر (Cursor، Codex، Gemini CLI، …)

هر ایجنتی که بتواند فایل بخواند، می‌تواند از ترجمان استفاده کند:

1. مخزن را کنار پروژه‌ات clone کن.
2. ابزارها را با `pip install` نصب کن (بالا).
3. در دستور سیستمی ایجنت، یا اول گفت‌وگو، بنویس:

   > پیش از هر ترجمه به فارسی، فایل `tarjoman/.claude/skills/tarjoman/SKILL.md` را بخوان و دقیقاً طبق آن کار کن. فقط راهنمای سبکی را بخوان که جدول بخش ۱ برای متن تو نشان می‌دهد.

برای Cursor، فایل `.cursorrules` ریشه‌ی مخزن را در پروژه‌ات کپی کن. برای Hermes، `agent-packs/hermes/SKILL.md` هست.

یا با یک دستور مهارت و تنظیمات MCP را برای ایجنت دلخواه نصب کن:

```bash
tarjoman install --target claude --with-mcp
tarjoman install --target cursor --with-mcp
tarjoman install --target antigravity --with-mcp
tarjoman install --target codex --with-mcp
tarjoman install --target hermes --with-mcp
```

---

## شروع سریع

### ترجمه

در Claude Code کافی است بخواهی:

> فایل `chapter1.md` رو به فارسی ترجمه کن و توی `chapter1.fa.md` بنویس.

ایجنت مهارت را خودش پیدا می‌کند. برای اینکه مطمئن شوی، بگو «با ترجمان». کاری که می‌کند:

1. سبک را تشخیص می‌دهد (مثلاً «رمان») و فقط `references/literary.md` را می‌خواند.
2. پیش‌نویس را می‌نویسد، بعد فقط فارسی را می‌خواند و جمله‌های ترجمه‌ای را از نو می‌نویسد.
3. با متن اصلی مقایسه می‌کند و این‌ها را اجرا می‌کند:

```bash
tarjoman verify chapter1.md chapter1.fa.md --json   # چیزی جا نیفتاده؟ عدد، پاراگراف، کد
tarjoman fix chapter1.fa.md --in-place               # اصلاح خودکار و امن ی/ک، نیم‌فاصله، تنوین و نقطه‌گذاری
tarjoman lint chapter1.fa.md --style literary        # نگارش، نیم‌فاصله، یکدستی لحن، گرته‌برداری
tarjoman lint chapter1.fa.md --errors-only --json    # فقط خطاهای قطعی نگارش با خروجی ساختاریافته
```

نمونه‌ی واقعی از همین مهارت (Kate Chopin، ۱۸۹۴):

| | |
|---|---|
| متن اصلی | Knowing that Mrs. Mallard was afflicted with a heart trouble, great care was taken to break to her as gently as possible the news of her husband's death. |
| ترجمه‌ی معمولی | با علم به اینکه خانم مالارد از بیماری قلبی رنج می‌برد، تلاش زیادی شد تا خبر مرگ شوهرش با نهایت ملایمت به او داده شود. |
| با ترجمان | می‌دانستند خانم مالارد ناراحتی قلبی دارد؛ برای همین خیلی مراقب بودند خبر مرگ شوهرش را تا جای ممکن آرام به او بدهند. |

### ویرایش متن فارسی ماشینی

> این متن رو روان کن، ولی هیچ واقعیتی رو حذف نکن: …

یا فقط برای تشخیص:

> کجای این متن ماشینی به نظر می‌رسه؟ بازنویسی نکن.

```bash
tarjoman lint post.md --only ai-tell --only calque
```

### زیرنویس (SRT و WebVTT)

```bash
tarjoman srt extract film.en.vtt -o film.cues.txt
tarjoman srt merge film.en.vtt film.fa.cues.txt -o film.fa.vtt
tarjoman srt check film.fa.srt --source film.en.srt --json   # تعداد، زمان، طول خط، سرعت خواندن
```

### فایل‌های ترجمه‌ی اپ و بازی (`i18n`)

```bash
tarjoman i18n check locales/en.json locales/fa.json --max-ratio 1.8 --json
```

### کتاب و EPUB

```bash
tarjoman book init "عنوان کتاب" -o ./my-book
tarjoman book glossary list
tarjoman book glossary import ./my-book technical-ai --json
tarjoman book characters ./my-book --add "Alice:آلیس:formal:تو"
tarjoman book terms ./my-book --add "Oh dear=وای خدا"
tarjoman book context ./my-book ch2.en.md --prev ch1.fa.md --json   # فقط اصطلاح و شخصیت همین تکه
tarjoman book check ./my-book ch1.en.md ch1.fa.md --json

tarjoman epub extract book.epub -o ./epub_work --json
tarjoman epub merge book.epub ./epub_work -o book.fa.epub --json
```

### اتصال مستقیم از طریق MCP (`tarjoman mcp`)

```json
{
  "mcpServers": {
    "tarjoman": { "command": "tarjoman", "args": ["mcp"] }
  }
}
```

راهنمای کامل کتاب: `.claude/skills/tarjoman/references/book.md` · یادداشت پژوهشی ارتقای کیفیت: `docs/research/translation-quality-roadmap.md` · داوری مقایسه‌ای کور (دقت و روانی، ۹۸ نمونه در همه‌ی ۲۲ سبک): `python benchmarks/run_judge.py --self-demo --provider heuristic`

---

## چه چیزی را نمی‌کند

- `tarjoman translate` بدون یک مدل زبانیِ وصل‌شده متن را ترجمه نمی‌کند. ترجمه کار ایجنت است.
- لینتر فقط الگوهای شناخته‌شده را می‌گیرد. بیشتر گرته‌برداری‌های واقعی معنایی‌اند و فقط بازنویسی خود مترجم آن‌ها را برطرف می‌کند (نتیجه‌ی آزمایش‌ها: `docs/research/real-texts/`).
- نمونه‌های «خوب» راهنماها را یک مدل نوشته و هنوز همه‌شان به دست یک فارسی‌زبان بازبینی نشده‌اند.

---

## ساختار مخزن

| مسیر | چیست |
|---|---|
| `.claude/skills/tarjoman/SKILL.md` | دستور اصلی ایجنت (کوتاه؛ به راهنمای سبک ارجاع می‌دهد) |
| `.claude/skills/tarjoman/references/` | راهنمای هر سبک، ویراستار، کتاب، چک‌لیست |
| `tarjoman/` | ابزارهای پایتونی (`lint`، `verify`، `srt check`، `book`، …) |
| `docs/research/` | آزمایش‌ها روی متن‌های واقعی و مجموعه‌ی ارزیابی |
| `agent-packs/` | نسخه‌ی Hermes و Cursor |

مجوز: MIT. سازنده: عرفان عاشوری ([@Erfix404](https://github.com/Erfix404)).

</div>
