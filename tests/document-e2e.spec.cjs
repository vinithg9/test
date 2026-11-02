const {test,expect}=require('@playwright/test');
const {Document,Paragraph,Packer}=require('docx');
const XLSX=require('xlsx');
const {PDFDocument}=require('pdf-lib');
const fs=require('fs');
const path=require('path');
const base='http://127.0.0.1:4173/docflow-single-file.html';
const fixture=path.resolve('test-fixtures');
test.beforeAll(async()=>{
 fs.mkdirSync(fixture,{recursive:true});
 const doc=new Document({sections:[{children:[new Paragraph('DOCFLOW_IMPORT_SENTINEL_8431')]}]});
 fs.writeFileSync(path.join(fixture,'sample.docx'),await Packer.toBuffer(doc));
 const wb=XLSX.utils.book_new();XLSX.utils.book_append_sheet(wb,XLSX.utils.aoa_to_sheet([['DOCFLOW_XLSX_SENTINEL',12],['total',{f:'B1*2'}]]),'Sheet1');
 XLSX.writeFile(wb,path.join(fixture,'sample.xlsx'));
 for(const [name,count] of [['sample.pdf',2],['second.pdf',1]]){
  const pdf=await PDFDocument.create();for(let i=0;i<count;i++)pdf.addPage([400,400]);
  fs.writeFileSync(path.join(fixture,name),await pdf.save());
 }
});
test.beforeEach(async({page})=>{await page.goto(base);});
async function upload(page,selector,files){
 const chooser=page.waitForEvent('filechooser');await page.locator(selector).click();await(await chooser).setFiles(files);
}
test('DOCX import and exported DOCX are readable',async({page})=>{
 await page.locator('[data-tool="word"]').click();
 await upload(page,'#word-open',path.join(fixture,'sample.docx'));
 await expect(page.locator('#word-editor')).toContainText('DOCFLOW_IMPORT_SENTINEL_8431',{timeout:15000});
 await page.locator('#word-editor').click();await page.keyboard.type(' EDITED_9921');
 const dl=page.waitForEvent('download',{timeout:20000});await page.locator('#word-save').click();
 const download=await dl;const out=test.info().outputPath('word-output.docx');await download.saveAs(out);
 const Mammoth=require('mammoth');const text=(await Mammoth.extractRawText({path:out})).value;
 expect(text).toContain('DOCFLOW_IMPORT_SENTINEL_8431');expect(text).toContain('EDITED_9921');
});
test('XLSX import, edit, and exported XLSX are readable',async({page})=>{
 await page.locator('[data-tool="excel"]').click();
 await upload(page,'#excel-open',path.join(fixture,'sample.xlsx'));
 const cell=page.locator('.sheet td[data-r="0"][data-c="0"]');
 await expect(cell).toContainText('DOCFLOW_XLSX_SENTINEL',{timeout:15000});
 await cell.fill('QA_EDITED_CELL');
 const dl=page.waitForEvent('download',{timeout:20000});await page.locator('#excel-save').click();
 const download=await dl;const out=test.info().outputPath('excel-output.xlsx');await download.saveAs(out);
 const wb=XLSX.readFile(out,{cellFormula:true});expect(wb.Sheets.Sheet1.A1.v).toBe('QA_EDITED_CELL');
});
test('PDF preview loads both pages',async({page})=>{
 await page.locator('[data-tool="pdf"]').click();
 await upload(page,'#pdf-open',path.join(fixture,'sample.pdf'));
 await expect(page.locator('#pdf-pages canvas')).toHaveCount(2,{timeout:20000});
});
test('PDF merge outputs three valid pages',async({page})=>{
 await page.locator('[data-tool="pdf"]').click();
 const chooser=page.waitForEvent('filechooser');await page.locator('#pdf-merge').click();
 const dl=page.waitForEvent('download',{timeout:20000});
 await(await chooser).setFiles([path.join(fixture,'sample.pdf'),path.join(fixture,'second.pdf')]);
 const download=await dl;const out=test.info().outputPath('merged.pdf');await download.saveAs(out);
 const pdf=await PDFDocument.load(fs.readFileSync(out));expect(pdf.getPageCount()).toBe(3);
});
