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
 * الأعمدة (مجال المبادرة، قرار الجهة، ملاحظات) للاستخدام الداخلي ويعبّئها الفريق.
 * المرفقات تُحفظ في مجلد «مرفقات مقترحات المبادرات» في Google Drive (خاص بكم)، ورابطها في عمود «المرفقات».
 * يصل إشعار نصي بكل مقترح إلى NOTIFY (بلا المرفقات، فهي في Drive). لإيقافه اجعله سلسلة فارغة.
 */
const SHEET_NAME = 'المقترحات';
const NOTIFY = 'info@uswah.sa';
const FOLDER_NAME = 'مرفقات مقترحات المبادرات';
const MAX_FILES = 3;

const COLUMNS = [
  ['ref', 'رقم المقترح'], ['received', 'تاريخ الاستلام'],
  ['name', 'الاسم'], ['org', 'الصفة / جهة العمل'], ['phone', 'رقم الجوال'], ['email', 'البريد الإلكتروني'],
  ['title', 'اسم المبادرة المقترح'], ['idea', 'فكرة المبادرة'], ['need', 'المشكلة أو الاحتياج'],
  ['audience', 'الفئة المستهدفة'], ['goals', 'أهداف المبادرة'], ['outputs', 'المخرجات المتوقعة'],
  ['impact', 'الأثر المتوقع'], ['partners', 'الشركاء أو الداعمون المحتملون'], ['cost', 'التكلفة التقديرية (ريال)'],
  ['role', 'الدور المرغوب'],
  ['_domain', 'مجال المبادرة (داخلي)'], ['_decision', 'قرار الجهة (داخلي)'], ['_notes', 'ملاحظات (داخلي)'],
  ['files', 'المرفقات'],
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
  // جدول أُنشئ بنسخة أقدم من السكربت: نضيف عناوين الأعمدة الجديدة إن نقصت
  if (sh.getLastColumn() < COLUMNS.length) {
    const from = sh.getLastColumn() + 1;
    sh.getRange(1, from, 1, COLUMNS.length - from + 1).setValues([COLUMNS.slice(from - 1).map(c => c[1])])
      .setFontWeight('bold').setBackground('#3a2236').setFontColor('#ffffff');
  }
  return sh;
}

function folder_() {
  const it = DriveApp.getFoldersByName(FOLDER_NAME);
  return it.hasNext() ? it.next() : DriveApp.createFolder(FOLDER_NAME);
}

// يحفظ المرفقات (base64) في Drive ويعيد روابطها، كل رابط في سطر
function saveFiles_(p) {
  const n = Math.min(Number(p.files) || 0, MAX_FILES), links = [];
  if (!n) return '';
  const dir = folder_();
  for (let k = 1; k <= n; k++) {
    const data = p['file' + k + '_data'];
    if (!data) continue;
    const name = String(p['file' + k + '_name'] || ('ملف ' + k)).slice(0, 150);
    const blob = Utilities.newBlob(Utilities.base64Decode(data), p['file' + k + '_type'] || 'application/octet-stream', (p.ref || '') + ' - ' + name);
    links.push(dir.createFile(blob).getUrl());
  }
  return links.join('\n');
}

function doPost(e) {
  const p = (e && e.parameter) || {};
  if (p.website) return ContentService.createTextOutput('ok');           // حقل الفخ: رسالة آلية
  if (!p.name || !p.title) return ContentService.createTextOutput('missing');   // الجوال والبريد اختياريان
  const lock = LockService.getScriptLock(); lock.waitLock(20000);
  try {
    const clean = v => String(v == null ? '' : v).slice(0, 2000).replace(/^[=+\-@]/, "'$&");  // يمنع تنفيذ الصيغ
    let files = '';
    try { files = saveFiles_(p); } catch (err) { files = 'تعذّر حفظ المرفقات: ' + err; }
    const row = COLUMNS.map(([k]) => k === 'received' ? new Date() : k === 'files' ? files : k.startsWith('_') ? '' : clean(p[k]));
    sheet_().appendRow(row);
  } finally { lock.releaseLock(); }
  if (NOTIFY) {
    try {
      MailApp.sendEmail(Object.assign({
        to: NOTIFY, subject: 'مقترح مبادرة جديد: ' + p.title + ' (' + (p.ref || '') + ')',
        body: COLUMNS.filter(([k]) => !k.startsWith('_') && k !== 'received' && k !== 'files' && k !== 'impact').map(([k, l]) => l + ': ' + (p[k] || '—')).join('\n'),
      }, /@/.test(p.email || '') ? { replyTo: p.email } : {}));
    } catch (err) { /* لا يوقف الحفظ */ }
  }
  return ContentService.createTextOutput('ok');
}

function doGet() { return ContentService.createTextOutput('uswah initiatives endpoint'); }
