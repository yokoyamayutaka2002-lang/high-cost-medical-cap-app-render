const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const { chromium } = require('playwright');

function sha256file(p){
  const data = fs.readFileSync(p);
  return crypto.createHash('sha256').update(data).digest('hex');
}

function findFirstSourceExcel(){
  // scan reports/*.json and return first source_file found
  const reportsDir = path.resolve(process.cwd(), 'reports');
  if(!fs.existsSync(reportsDir)) return null;
  const files = fs.readdirSync(reportsDir).filter(f=>f.endsWith('.json'));
  for(const f of files){
    try{
      const obj = JSON.parse(fs.readFileSync(path.join(reportsDir,f),'utf8'));
      const issues = obj.issues || obj;
      if(Array.isArray(issues)){
        for(const it of issues){
          if(it && it.source_file){
            return it.source_file;
          }
        }
      }
      // fallback: top-level source_file
      if(obj.source_file) return obj.source_file;
    }catch(e){ console.warn('skip',f,e.message); }
  }
  return null;
}

function readIssuesAll(){
  // merge all reports issues arrays
  const reportsDir = path.resolve(process.cwd(), 'reports');
  const out = [];
  if(!fs.existsSync(reportsDir)) return out;
  const files = fs.readdirSync(reportsDir).filter(f=>f.endsWith('.json'));
  for(const f of files){
    try{
      const obj = JSON.parse(fs.readFileSync(path.join(reportsDir,f),'utf8'));
      const issues = obj.issues || obj;
      if(Array.isArray(issues)) out.push(...issues);
    }catch(e){ console.warn('skip',f,e.message); }
  }
  return out;
}

async function run(){
  const repoRoot = process.cwd();
  const excelRel = findFirstSourceExcel();
  if(!excelRel){
    console.error('No source excel found in reports/ JSONs. Aborting.');
    process.exit(2);
  }
  const excelPath = path.resolve(repoRoot, excelRel);
  if(!fs.existsSync(excelPath)){
    console.error('Excel file referenced by reports not found:', excelPath);
    process.exit(3);
  }

  const issues = readIssuesAll();

  const artifactsDir = path.resolve(repoRoot,'artifacts');
  const screenshotsDir = path.join(artifactsDir,'screenshots');
  fs.mkdirSync(screenshotsDir, { recursive: true });

  const browser = await chromium.launch({ args: ['--no-sandbox'] });
  const context = await browser.newContext({ viewport: { width:1440, height:900 } });
  const page = await context.newPage();

  const viewerPath = path.resolve(repoRoot,'web','viewer.html');
  const viewerUrl = 'file://' + viewerPath;
  await page.goto(viewerUrl, { waitUntil: 'load' });

  // attach files to inputs
  const excelInput = await page.$('input#excelFile');
  const jsonInput = await page.$('input#jsonFile');
  if(!excelInput || !jsonInput){
    console.error('Viewer inputs not found in DOM');
    await browser.close(); process.exit(4);
  }

  await excelInput.setInputFiles(excelPath);

  // write a merged issues file temporarily to pass to the input
  const tmpIssuesPath = path.join(artifactsDir,'_tmp_issues.json');
  fs.writeFileSync(tmpIssuesPath, JSON.stringify({ issues }, null, 2), 'utf8');
  await jsonInput.setInputFiles(tmpIssuesPath);

  // small helper to set checkbox state
  async function setCheckbox(selector, checked){
    await page.evaluate(({selector, checked})=>{
      const el = document.querySelector(selector);
      if(!el) return;
      el.checked = checked;
      el.dispatchEvent(new Event('change', { bubbles:true }));
    }, { selector, checked });
  }

  // ensure the page has processed load
  await page.waitForTimeout(800);

  const patterns = [];
  // pattern-1: errors + warnings on
  patterns.push({ name:'review_all_issues.png', filters:{ errors:true, warnings:true } });
  // pattern-2: errors only
  patterns.push({ name:'review_errors_only.png', filters:{ errors:true, warnings:false } });
  // pattern-3: warnings only (only if there are warnings)
  const anyWarning = issues.some(i=>i.level==='warning');
  if(anyWarning) patterns.push({ name:'review_warnings_only.png', filters:{ errors:false, warnings:true } });

  const produced = [];
  for(const p of patterns){
    // set filter checkboxes
    await setCheckbox('#filterErrors', !!p.filters.errors);
    await setCheckbox('#filterWarnings', !!p.filters.warnings);

    // wait for highlight application (heuristic)
    await page.waitForTimeout(600);

    // click first issue to set activeIndex=0 if exists
    const firstIssue = await page.$('#issueList .issue-item');
    if(firstIssue){
      await firstIssue.click();
      await page.waitForTimeout(300);
    }

    const outPath = path.join(screenshotsDir, p.name);
    await page.screenshot({ path: outPath, fullPage: true });
    console.log('Saved', outPath);
    produced.push({ file: `screenshots/${p.name}`, filter: p.filters });
  }

  // manifest
  const generatedAt = (new Date()).toISOString();
  const sourceExcel = path.basename(excelPath);
  const sourceHash = sha256file(excelPath);

  // mapping_version: try read data/mapping.yaml 'version' or fallback to sha256
  let mappingVersion = null;
  const mappingPath = path.resolve(repoRoot,'data','mapping.yaml');
  if(fs.existsSync(mappingPath)){
    try{
      const txt = fs.readFileSync(mappingPath,'utf8');
      const m = txt.match(/^version:\s*(.+)$/m);
      if(m) mappingVersion = m[1].trim(); else mappingVersion = crypto.createHash('sha256').update(txt).digest('hex');
    }catch(e){ mappingVersion = null; }
  }

  // validator_version: prefer GITHUB_SHA env
  const validatorVersion = process.env.GITHUB_SHA || (await (async ()=>{ try{ const { execSync } = require('child_process'); return execSync('git rev-parse --short HEAD').toString().trim(); }catch(e){ return null; } })());

  const totalIssues = issues.length;
  const errors = issues.filter(i=>i.level==='error').length;
  const warnings = issues.filter(i=>i.level==='warning').length;

  // copy source excel into artifacts/excel/source.xlsx
  const excelDestDir = path.join(artifactsDir,'excel');
  fs.mkdirSync(excelDestDir, { recursive: true });
  const excelDest = path.join(excelDestDir, 'source.xlsx');
  fs.copyFileSync(excelPath, excelDest);

  // write validation report (merged issues) into artifacts/validation/validation_report.json
  const valDir = path.join(artifactsDir,'validation');
  fs.mkdirSync(valDir, { recursive: true });

  // augment issues with screenshot_ref (primary best-fit)
  const augmentedIssues = issues.map(it => {
    const copy = Object.assign({}, it);
    if(copy.level === 'error'){
      copy.screenshot_ref = produced.find(p=>p.file.includes('errors_only')) ? 'review_errors_only' : 'review_all_issues';
    } else if(copy.level === 'warning'){
      copy.screenshot_ref = produced.find(p=>p.file.includes('warnings_only')) ? 'review_warnings_only' : 'review_all_issues';
    } else {
      copy.screenshot_ref = 'review_all_issues';
    }
    return copy;
  });

  const validationReportPath = path.join(valDir,'validation_report.json');
  fs.writeFileSync(validationReportPath, JSON.stringify({ issues: augmentedIssues }, null, 2), 'utf8');

  const manifest = {
    generated_at: generatedAt,
    source_excel: sourceExcel,
    source_hash: sourceHash,
    mapping_version: mappingVersion,
    validator_version: validatorVersion,
    total_issues: totalIssues,
    errors: errors,
    warnings: warnings,
    screenshots: produced,
    artifacts: {
      excel: { path: 'excel/source.xlsx' },
      validation: { path: 'validation/validation_report.json' },
      screenshots: produced
    },
    index: { path: 'index.html' }
  };

  const manifestPath = path.join(artifactsDir,'manifest.json');
  fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2), 'utf8');
  console.log('Wrote manifest at artifacts/manifest.json');

  // generate static index.html in artifacts
  const indexHtml = buildIndexHtml(manifest, augmentedIssues);
  fs.writeFileSync(path.join(artifactsDir,'index.html'), indexHtml, 'utf8');
  console.log('Wrote artifacts/index.html');

  await browser.close();
  process.exit(0);
}

// ----------------------- helper to build index.html -----------------------
function escapeHtml(s){ return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }

function buildIndexHtml(manifest, issues){
  // Build a self-contained static HTML that references local artifact files
  const screenshots = manifest.screenshots || [];
  const rowsHtml = (issues || []).map(i=>{
    const ref = i.screenshot_ref || 'review_all_issues';
    const thumb = screenshots.find(s=>s.file.includes(ref)) ? screenshots.find(s=>s.file.includes(ref)).file : (screenshots[0] ? screenshots[0].file : '');
    const thumbPath = thumb ? thumb : '';
    return `<tr>
      <td>${escapeHtml(i.rule||'')}</td>
      <td>${escapeHtml(i.level||'')}</td>
      <td>${escapeHtml(i.message || i.rule || '')}</td>
      <td>${escapeHtml(String(i.row||''))}</td>
      <td>${escapeHtml(String(i.column||''))}</td>
      <td>${ thumbPath ? `<a href="#${ref}"><img src="${thumbPath}" style="height:80px;" alt="${ref}"/></a>` : '' }</td>
    </tr>`;
  }).join('\n');

  const galleryHtml = screenshots.map(s => {
    const id = s.file.replace(/\W+/g,'_');
    return `<div style="display:inline-block;margin:8px;text-align:center;">
      <a id="${s.file.replace(/\W+/g,'_')}" href="${s.file}"><img src="${s.file}" style="max-width:240px;max-height:160px;border:1px solid #ccc;display:block;"/></a>
      <div style="font-size:0.9em;margin-top:6px;">${escapeHtml(s.file)}<br/><span style="color:#666;font-size:0.85em;">filters: ${s.filter? `errors=${s.filter.errors}, warnings=${s.filter.warnings}`:''}</span></div>
    </div>`;
  }).join('\n');

  const index = `<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Validation Artifacts Hub</title>
  <style>
    body{font-family:system-ui,Segoe UI,Roboto,Arial;margin:20px}
    table{border-collapse:collapse;width:100%}
    th,td{border:1px solid #ddd;padding:8px}
    th{background:#f4f6f8}
    .summary{margin-bottom:16px}
  </style>
</head>
<body>
  <h2>Validation Artifacts Hub</h2>
  <div class="summary">
    <div><strong>Source Excel:</strong> <a href="${manifest.artifacts.excel.path}">${escapeHtml(manifest.source_excel || '')}</a></div>
    <div><strong>Source Hash:</strong> ${escapeHtml(manifest.source_hash || '')}</div>
    <div><strong>Mapping Version:</strong> ${escapeHtml(manifest.mapping_version || '')}</div>
    <div><strong>Validator Version:</strong> ${escapeHtml(manifest.validator_version || '')}</div>
    <div><strong>Errors / Warnings:</strong> ${manifest.errors || 0} / ${manifest.warnings || 0}</div>
  </div>

  <h3>Quick Links</h3>
  <ul>
    <li>📄 <a href="${manifest.artifacts.excel.path}">Source Excel (download)</a></li>
    <li>📊 <a href="${manifest.artifacts.validation.path}">Validation JSON (download / view)</a></li>
    <li>🖼 <a href="#gallery">Screenshots Gallery</a></li>
  </ul>

  <h3>Issues Table</h3>
  <table>
    <thead><tr><th>rule_id</th><th>level</th><th>message</th><th>row</th><th>column</th><th>screenshot</th></tr></thead>
    <tbody>
    ${rowsHtml}
    </tbody>
  </table>

  <h3 id="gallery">Screenshot Gallery</h3>
  <div>${galleryHtml}</div>

  <hr/>
  <div style="margin-top:20px;font-size:0.9em;color:#555">This page is a static hub generated by CI. Open the files above to download or inspect artifacts.</div>
</body>
</html>`;

  return index;
}

run().catch(e=>{ console.error(e); process.exit(10); });
