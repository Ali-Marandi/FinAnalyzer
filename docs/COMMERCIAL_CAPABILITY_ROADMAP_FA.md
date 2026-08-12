# نقشه‌راه قابلیت‌های تجاری FinAnalyzer Enterprise

FinAnalyzer اکنون پایه‌های مهم یک محصول مالی سازمانی را دارد: ثبت دوطرفه، چندشرکتی، اتصال بانکی، گزارش PDF/Excel، RBAC، SSO/MFA، DPAPI، audit chain و کنترل وابستگی انتشار. گام بعدی باید تبدیل این پایه به فرایندهای مالی کنترل‌شده، قابل‌پیش‌بینی و قابل‌فروش به سازمان‌ها باشد.

## قابلیت پیاده‌سازی‌شده در این چرخه: بستن دوره مالی با کنترل دو نفره

قابلیت جدید **Controlled Financial Period Close** در لایه سرویس، مدل داده، RBAC، audit و رابط دسکتاپ اضافه شد. کاربر دارای مجوز `ledger.period.close.request` و MFA تازه، درخواست بستن دوره می‌سازد. سپس یک Financial Controller مستقل با مجوز `ledger.period.close.approve` و MFA تازه آن را تأیید و اجرا می‌کند. درخواست‌کننده نمی‌تواند درخواست خود را تأیید یا رد کند؛ این تخلف تفکیک وظایف به‌صورت رخداد audit با نتیجه `denied` ثبت می‌شود.

| لایه | پیاده‌سازی جدید | ارزش تجاری |
|---|---|---|
| مدل داده | `PeriodCloseRequest` و وضعیت‌های pending/approved/rejected/executed | شفافیت چرخه بستن دوره |
| RBAC | دو permission حساس و نقش `financial_controller` | تفکیک وظایف و کنترل MFA |
| حسابداری | commit قابل‌کنترل برای close atomic | جلوگیری از وضعیت نیمه‌کاره |
| پایگاه داده | index یکتا برای یک درخواست فعال به ازای هر دوره | جلوگیری از close موازی |
| ممیزی | رخدادهای request، execute و SoD violation در HMAC chain | شواهد قابل‌راستی‌آزمایی |
| رابط کاربری | صفحه **Period Close Controls** | دسترسی عملیاتی برای تیم مالی |

> این کنترل برای کاهش ریسک تغییرات بدون تأیید در دوره‌های بسته طراحی شده است؛ جایگزین policyهای حسابداری، بازبینی حسابرس یا کنترل‌های قانونی محلی نیست.

## اولویت‌های پیشنهادی پس از این چرخه

| اولویت | قابلیت | مسئله تجاری که حل می‌کند | محدوده پیشنهادی |
|---:|---|---|---|
| ۱ | Bank Reconciliation Workbench | تطبیق کنترل‌شده bank feed با دفترکل و مدیریت استثنا | matching rules، صف exception، تأیید/رد و audit |
| ۲ | AP/Expense Approval Workflow | کنترل خرید، هزینه و پرداخت پیش از اثر مالی | آستانه مبلغ، چندمرحله‌ای، delegation، SoD و payment hold |
| ۳ | Rolling Cash Forecast | دید نقدینگی ۱۳ هفته‌ای برای مدیر مالی | سناریوها، confidence range، ورودی بانک/AR/AP و variance tracking |
| ۴ | Multi-Entity Consolidation | گزارش گروهی برای شرکت‌های هلدینگ | mapping حساب‌ها، eliminations، نرخ ارز و consolidation close |
| ۵ | Close Calendar & Checklist | استانداردسازی کارهای پایان ماه و مسئولیت‌ها | task ownership، due date، evidence attachment و escalation |
| ۶ | Audit & SIEM Export | ارسال شواهد security به SOC/Compliance | export امضاشده، retention policy، Microsoft Sentinel/Splunk connector |
| ۷ | Access Review & Attestation | بازبینی دوره‌ای نقش‌ها و دسترسی‌ها | campaign فصلی، manager attestation و revoke workflow |
| ۸ | Encrypted Backup & Disaster Recovery | تاب‌آوری عملیاتی و recovery قابل‌تست | backup رمزنگاری‌شده، restore drill، RPO/RTO evidence |
| ۹ | Policy-Based Auto-Update | ارائه patch امن desktop به مشتریان | manifest امضاشده، حلقه انتشار و rollback کنترل‌شده |
| ۱۰ | Executive Mobile Approvals | تصمیم‌گیری سریع مدیران خارج از دفتر | approval محدود، MFA، push notification و no-data-at-rest |

## مسیر تحویل پیشنهادی

در انتشار بعدی، **Bank Reconciliation Workbench** باید اولویت نخست باشد؛ زیرا اتصال Plaid بدون reconciliation workflow تنها داده وارد می‌کند، اما محصول تجاری باید تصمیم‌گیری، استثنا، مسئولیت و قابلیت ممیزی ایجاد کند. پس از آن AP approvals و cash forecast بیشترین هم‌افزایی را با مشتریان مالی سازمانی دارند.

| موج | خروجی | معیار پذیرش |
|---|---|---|
| موج ۱ | Reconciliation queue و matching قابل‌توضیح | هر تطبیق یا override در audit ثبت شود و از scope شرکت خارج نشود |
| موج ۲ | Approval engine برای AP/expense | درخواست‌کننده نتواند approval نهایی خود را بدهد |
| موج ۳ | Cash forecast و سناریو | ورودی‌ها versioned، assumptions قابل‌ردیابی و نتایج قابل export باشند |
| موج ۴ | Consolidation و close calendar | eliminations و task evidence به‌صورت tenant-scoped نگهداری شوند |

تمام قابلیت‌های آینده باید از اصول فعلی FinAnalyzer پیروی کنند: **deny-by-default، MFA برای عملیات حساس، company-scoping، حداقل‌سازی داده در audit، و اعتبارسنجی زنجیره HMAC پیش از هر export انطباقی.**
