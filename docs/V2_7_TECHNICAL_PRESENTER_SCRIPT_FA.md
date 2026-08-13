# اسکریپت کامل ارائه فنی FinAnalyzer Enterprise v2.7.0

## Cover

**عنوان اسلاید:** FinAnalyzer Enterprise v2.7.0

**زیرعنوان:** تطبیق بانکی کنترل‌شده، Close قابل‌راستی‌آزمایی و مسیر هوشمند v2.8.0

**متن ارائه:**

«در این ارائه نشان می‌دهم که نسخه ۲.۷.۰ چگونه فاصله میان ورود خودکار bank feed و کنترل حسابداری سازمانی را پر می‌کند. موضوع اصلی صرفاً اتصال بانکی نیست؛ موضوع، تبدیل داده بانکی به تصمیم مالی قابل‌ردیابی، مجاز و آماده برای بستن دوره است. سپس مسیر پیشنهادی برای نسخه هوشمند ۲.۸.۰ را مرور می‌کنم.»

## Slide 1 — مسئله: ورود بانکی بدون review، ریسک close است

**محتوای اسلاید:**

- Bank feed باید سریع وارد شود، اما طبقه‌بندی نهایی نیازمند evidence انسانی است.
- تراکنش pending، provider revision و removal می‌توانند وضعیت دفتر را تغییر دهند.
- بستن دوره فقط با نبود تراکنش pending امن نیست؛ مورد posted اما بررسی‌نشده نیز باید blocker باشد.

**متن ارائه:**

«در فرآیندهای مالی مدرن، سرعت و کنترل باید هم‌زمان وجود داشته باشند. اگر همه چیز منتظر review بماند، visibility عملیاتی از بین می‌رود. اگر همه چیز بلافاصله نهایی تلقی شود، بستن دوره با طبقه‌بندی نادرست انجام می‌شود. v2.7.0 این دوگانه را با ورود متوازن اولیه و review کنترل‌شده بعدی حل می‌کند.»

## Slide 2 — معماری: sync اتمیک، review مستقل

**محتوای اسلاید:**

- Plaid sync همه added/modified/removed را در transaction واحد اعمال می‌کند.
- cursor تنها بعد از موفقیت کامل جلو می‌رود؛ failure باعث rollback mapping، entry و cursor می‌شود.
- هر ورود یا revision به `needs_review` بازمی‌گردد.

**متن ارائه:**

«در لایه integration، ابتدا کل update از provider جمع‌آوری می‌شود. سپس در یک تراکنش محلی apply می‌گردد. اگر هر بخش—برای مثال قفل بودن دوره—خطا بدهد، هیچ cursor جدیدی ثبت نمی‌شود. این ویژگی از تکرار ناقص یا داده نیمه‌اعمال‌شده جلوگیری می‌کند. پس از موفقیت نیز تراکنش جدید قطعیِ حسابداری نیست؛ فقط آماده review است.»

## Slide 3 — چهار وضعیت، یک سیاست روشن

**محتوای اسلاید:**

| وضعیت | معنا | اثر در close |
|---|---|---|
| `needs_review` | ورود یا revision جدید | blocker |
| `exception` | نیازمند رسیدگی مستقل | blocker |
| `matched` | contra account تأیید شده | مجاز |
| `removed` | provider حذف کرده است | از صف review خارج |

**متن ارائه:**

«وضعیت‌ها عمداً کم و صریح‌اند. `needs_review` یعنی سیستم هنوز نمی‌گوید این هزینه یا درآمد به چه حسابی تعلق دارد. `exception` یعنی reviewer تشخیص داده evidence کافی نیست یا مورد غیرعادی است. فقط `matched` اجازه عبور به close می‌دهد. `removed` نیز یک تصمیم provider است که فقط در دوره باز می‌تواند entry متناظر را void کند.»

## Slide 4 — SoD: permission کافی نیست؛ هویت actor کنترل می‌شود

**محتوای اسلاید:**

- `bank.reconcile.match` برای طبقه‌بندی اولیه و `bank.reconcile.exception.resolve` برای رفع exception تعریف شده‌اند.
- عملیات حساس به MFA تازه و company scope وابسته‌اند.
- ثبت‌کننده exception نمی‌تواند همان exception را resolve کند؛ انکار در HMAC audit ثبت می‌شود.

**متن ارائه:**

«نکته کلیدی این است که صرف دادن دو permission به یک نقش، SoD را کامل نمی‌کند. ما روی خود mapping بررسی می‌کنیم که user حل‌کننده همان user ثبت‌کننده exception نباشد. بنابراین حتی Finance Manager یا Company Admin که هر دو permission را دارد، نمی‌تواند exception خودش را resolve کند. این کنترل با actor واقعی session اجرا می‌شود، نه با وضعیت UI.»

## Slide 5 — تمامیت دفتر: فقط contra line تغییر می‌کند

**محتوای اسلاید:**

- service خط بانک را شناسایی و انتخاب همان حساب به‌عنوان contra را رد می‌کند.
- ساختار غیرمنتظره، account خارج از scope یا account غیرفعال، عملیات را متوقف می‌کند.
- مبلغ، تاریخ و تعداد lineها تغییر نمی‌کنند؛ debit/credit متوازن باقی می‌ماند.

**متن ارائه:**

«فضای تطبیق، ابزار ساخت entry جدید نیست. سرویس انتظار یک entry posted با یک خط بانک و دقیقاً یک خط contra دارد. فقط account_id خط contra تغییر می‌کند. اگر ساختار بیش از این باشد، سیستم حدس نمی‌زند؛ آن را exception تلقی می‌کند. این محدودیت، پاسخ‌گویی و قابلیت حسابرسی را بالا می‌برد.»

## Slide 6 — Close Readiness: کنترل در دو نقطه اجرا می‌شود

**محتوای اسلاید:**

- پیش از request close، readiness تمام blockerها را ارزیابی می‌کند.
- پیش از approval/execution، همان ارزیابی دوباره انجام می‌شود.
- `pending_bank_transactions` و `unreconciled_bank_transactions` بستن دوره را متوقف می‌کنند.

**متن ارائه:**

«Readiness یک گزارش نمایشی نیست؛ gate واقعی workflow است. ممکن است در فاصله request و approval یک sync جدید انجام شود. به همین دلیل کنترل یک‌بار نیست و درست پیش از اجرای close تکرار می‌شود. این رویکرد از race condition بین عملیات بانکی و بستن دوره جلوگیری می‌کند.»

## Slide 7 — Audit قابل‌راستی‌آزمایی و evidence عملیاتی

**محتوای اسلاید:**

- match، exception، resolution و SoD denial با actor، company، session و target ثبت می‌شوند.
- HMAC-SHA256 chain ترتیب و محتوا را به هم متصل می‌کند.
- Compliance Evidence Pack، manifest هش‌شده و خروجی audit-verified تولید می‌کند.

**متن ارائه:**

«هر تصمیم reconciliation فقط یک تغییر داده نیست؛ evidence است. Audit event به mapping مشخص، principal مشخص و company مشخص وصل می‌شود. زنجیره HMAC امکان تشخیص تغییر محلی در محتوا یا ترتیب رخدادها را فراهم می‌کند. سپس Compliance Evidence Pack می‌تواند این شواهد را در قالبی قابل‌تحویل به حسابرس جمع کند.»

## Slide 8 — تجربه دسکتاپ: صف امن، نه raw feed

**محتوای اسلاید:**

- صفحه Bank Reconciliation تنها شناسه، تاریخ، توضیح، مبلغ، وضعیت و note را نشان می‌دهد.
- raw provider payload در صف UI نمایش داده نمی‌شود.
- سه عمل کنترل‌شده: Match، Flag Exception و Resolve Exception.

**متن ارائه:**

«در سطح UI نیز اصل کمینه‌سازی داده رعایت شده است. کاربر فقط همان اطلاعاتی را می‌بیند که برای review لازم است؛ payload خام provider در صف نمایش داده نمی‌شود. با این حال، دکمه‌ها اعتماد امنیتی ایجاد نمی‌کنند؛ هر عمل مجدداً در service layer authorize و audit می‌شود.»

## Slide 9 — اعتبارسنجی تا امضای Windows، یک زنجیره کنترل

**محتوای اسلاید:**

- ۵ تست اختصاصی reconciliation و سناریوهای Plaid برای rollback، lock و SoD؛ کل release با ۴۰ تست و dependency gate اعتبارسنجی شد.
- GitHub Actions روی revision immutable actionها قفل شده و OIDC کوتاه‌عمر جای PFX در repository را می‌گیرد.
- Azure Artifact Signing، RFC 3161 timestamp و `production-signing` با reviewer مستقل، artifact قابل‌راستی‌آزمایی تولید می‌کنند.

**متن ارائه:**

«ارزش کنترل به قابلیت آزمون و انتشار ایمن آن است. ما happy path را تنها معیار ندانسته‌ایم؛ انکار self-resolution، دوره بسته و rollback بانکی هم regression test دارند. سپس خط لوله Windows، بدون PFX در repository، OIDC کوتاه‌عمر، signature و timestamp را قبل از upload کنترل می‌کند. فعال‌سازی واقعی این مسیر نیازمند تکمیل Azure و policy محیط production است.»

## Slide 10 — v2.8: هوش مالی، اما با human approval

**محتوای اسلاید:**

- اولویت: Statement Reconciliation Intelligence با CSV/OFX، match قطعی و پیشنهاد قابل‌توضیح.
- برای مبلغ بالا، split match، ارز یا vendor پرریسک، policy-driven dual approval اعمال می‌شود.
- مدل هوشمند فقط پیشنهاد می‌دهد؛ mutation دفتر پس از permission، MFA و approval انسانی انجام می‌شود.

**متن ارائه:**

«پیشنهاد v2.8.0 این است که از داده statement واقعی به سمت matching هوشمند حرکت کنیم. اما هوشمندی بدون governance، ریسک را جابه‌جا می‌کند. بنابراین مدل باید score و explanation بدهد، نه اینکه خودکار کتابداری کند. در موارد با ریسک بالا، policy یک reviewer مستقل و شواهد بیشتر می‌خواهد.»

## Slide 11 — تصمیم پیشنهادی

**محتوای اسلاید:**

- v2.7.0: کنترل عملیاتی bank feed و close آماده است.
- گام بعدی: تصویب discovery و طراحی v2.8.0-a برای deterministic statement matching و decision history.
- معیار خروج: UAT مالی، policy approval، تست هم‌زمانی و evidence export.

**متن ارائه:**

«جمع‌بندی این است که v2.7.0 یک پایه کنترل‌شده برای تطبیق بانکی ایجاد کرده است. تصمیم پیشنهادی برای هیئت‌مدیره یا تیم محصول، آغاز v2.8.0-a با دامنه محدود اما ارزشمند است: import statement، match قطعی، history تصمیم و optimistic concurrency. پس از آن، قابلیت‌های AI و split matching با داده واقعی و UAT مالی توسعه داده می‌شوند.»
