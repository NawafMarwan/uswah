/**
 * يستقبل مقترحات صفحة uswah.sa/initiatives ويحفظها في جدول Google.
 *
 * طريقة التركيب (مرة واحدة):
 *  1) أنشئ جدول Google جديدًا باسم «مقترحات المبادرات».
 *  2) من القائمة: الإضافات (Extensions) ← Apps Script، واحذف ما فيه والصق هذا الملف كاملًا، ثم احفظ.
 *  3) نشر (Deploy) ← نشر جديد (New deployment) ← النوع: تطبيق ويب (Web app)
 *       - التنفيذ باسم (Execute as): أنا (Me)
 *       - من يمكنه الوصول (Who has access): أي شخص (Anyone)
 *     ثم «نشر»، ووافق على الصلاحيات، وانسخ رابط تطبيق الويب (ينتهي بـ /exec).
 *  4) ضع الرابط في initiatives/index.html في السطر:  const ENDPOINT = '...';
 *
 * الأعمدة الأخيرة (مجال المبادرة، قرار الجهة، ملاحظات) للاستخدام الداخلي ويعبّئها الفريق.
 * لتلقي إشعار بريدي بكل مقترح جديد عدّل NOTIFY أدناه (اتركه فارغًا لإيقافه).
 */
const SHEET_NAME = 'المقترحات';
const NOTIFY = 'info@uswah.sa';

const COLUMNS = [
  ['ref', 'رقم المقترح'], ['received', 'تاريخ الاستلام'],
  ['name', 'الاسم'], ['org', 'الصفة / جهة العمل'], ['phone', 'رقم الجوال'], ['email', 'البريد الإلكتروني'],
  ['title', 'اسم المبادرة المقترح'], ['idea', 'فكرة المبادرة'], ['need', 'المشكلة أو الاحتياج'],
  ['audience', 'الفئة المستهدفة'], ['goals', 'أهداف المبادرة'], ['outputs', 'المخرجات المتوقعة'],
  ['impact', 'الأثر المتوقع'], ['partners', 'الشركاء أو الداعمون المحتملون'], ['cost', 'التكلفة التقديرية (ريال)'],
  ['role', 'الدور المرغوب'],
  ['_domain', 'مجال المبادرة (داخلي)'], ['_decision', 'قرار الجهة (داخلي)'], ['_notes', 'ملاحظات (داخلي)'],
];

function sheet_() {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  let sh = ss.getSheetByName(SHEET_NAME);
  if (!sh) {
    sh = ss.insertSheet(SHEET_NAME);
    sh.appendRow(COLUMNS.map(c => c[1]));
    sh.setFrozenRows(1);
    sh.getRange(1, 1, 1, COLUMNS.length).setFontWeight('bold').setBackground('#3a2236').setFontColor('#ffffff');
    sh.setRightToLeft(true);
    const domains = ['استراتيجيات وخطط', 'سياسات ولوائح وأدلة حوكمة', 'برامج وخدمات ومنتجات', 'شراكات وتحالفات', 'تنمية موارد مالية',
      'تطوع ومشاركة مجتمعية', 'بناء قدرات وتدريب', 'دراسات وتقارير وقياس أثر', 'توعية وحملات'];
    const col = n => COLUMNS.findIndex(c => c[0] === n) + 1;
    sh.getRange(2, col('_domain'), 2000, 1).setDataValidation(SpreadsheetApp.newDataValidation().requireValueInList(domains, true).build());
    sh.getRange(2, col('_decision'), 2000, 1).setDataValidation(SpreadsheetApp.newDataValidation().requireValueInList(['قبول', 'يحتاج إلى تطوير', 'اعتذار'], true).build());
  }
  return sh;
}

function doPost(e) {
  const p = (e && e.parameter) || {};
  if (p.website) return ContentService.createTextOutput('ok');           // حقل الفخ: رسالة آلية
  if (!p.name || !p.email || !p.title) return ContentService.createTextOutput('missing');
  const lock = LockService.getScriptLock(); lock.waitLock(20000);
  try {
    const clean = v => String(v == null ? '' : v).slice(0, 2000).replace(/^[=+\-@]/, "'$&");  // يمنع تنفيذ الصيغ
    const row = COLUMNS.map(([k]) => k === 'received' ? new Date() : k.startsWith('_') ? '' : clean(p[k]));
    sheet_().appendRow(row);
  } finally { lock.releaseLock(); }
  if (NOTIFY) {
    try {
      MailApp.sendEmail({
        to: NOTIFY, subject: 'مقترح مبادرة جديد: ' + p.title + ' (' + (p.ref || '') + ')',
        body: COLUMNS.filter(([k]) => !k.startsWith('_') && k !== 'received').map(([k, l]) => l + ': ' + (p[k] || '—')).join('\n'),
        replyTo: p.email,
      });
    } catch (err) { /* لا يوقف الحفظ */ }
  }
  return ContentService.createTextOutput('ok');
}

function doGet() { return ContentService.createTextOutput('uswah initiatives endpoint'); }
