(function(){
  // ValidationHighlighter + simple ExcelViewer glue

  // ---------------- ExcelViewer (minimal) ----------------
  const ExcelViewer = {
    workbook: null,
    currentSheet: null,
    loadWorkbook(wb){
      this.workbook = wb;
      const names = wb.SheetNames || [];
      const toolbar = document.getElementById('sheetToolbar');
      toolbar.innerHTML = '';
      names.forEach((n, idx)=>{
        const btn = document.createElement('button');
        btn.textContent = n;
        btn.addEventListener('click', ()=> this.renderSheet(n));
        toolbar.appendChild(btn);
      });
      if(names.length) this.renderSheet(names[0]);
    },
    renderSheet(name){
      const sheet = this.workbook.Sheets[name];
      if(!sheet) return;
      this.currentSheet = name;
      const data = XLSX.utils.sheet_to_json(sheet, {header:1, defval:''});
      const container = document.getElementById('sheetContainer');
      container.innerHTML = '';
      const table = document.createElement('table');
      table.className = 'sheet';

      // assume first row is header
      const headerRow = data[0] || [];

      const thead = document.createElement('thead');
      const trh = document.createElement('tr');
      const thRowNum = document.createElement('th');
      thRowNum.className = 'row-num header-row';
      thRowNum.textContent = '#';
      trh.appendChild(thRowNum);
      for(let c=0;c<headerRow.length;c++){
        const th = document.createElement('th');
        th.textContent = headerRow[c] || '';
        trh.appendChild(th);
      }
      thead.appendChild(trh);
      table.appendChild(thead);

      const tbody = document.createElement('tbody');
      for(let r=1;r<data.length;r++){
        const tr = document.createElement('tr');
        const rowNum = document.createElement('td');
        rowNum.className = 'row-num';
        const excelRowNumber = r+1; // because header is row 1
        rowNum.textContent = excelRowNumber;
        tr.appendChild(rowNum);
        const row = data[r] || [];
        for(let c=0;c<headerRow.length;c++){
          const td = document.createElement('td');
          const colName = headerRow[c] || `C${c+1}`;
          td.setAttribute('data-row', String(excelRowNumber));
          td.setAttribute('data-col-index', String(c));
          td.setAttribute('data-col-name', String(colName));
          td.textContent = (row[c] !== undefined && row[c] !== null) ? String(row[c]) : '';
          tr.appendChild(td);
        }
        tbody.appendChild(tr);
      }
      table.appendChild(tbody);
      container.appendChild(table);

      // after rendering, notify highlighter to recompute highlights
      if(window.ValidationHighlighter) window.ValidationHighlighter.reapplyHighlights();
    }
  };

  // ---------------- ValidationHighlighter ----------------
  const ValidationHighlighter = (function(){
    const state = {
      showErrors: true,
      showWarnings: true,
      enabledRules: new Set(),
      issues: [], // original array reference
      filteredIssues: [],
      activeIndex: 0,
    };

    // DOM refs
    const rulesContainer = () => document.getElementById('rulesContainer');
    const issueList = () => document.getElementById('issueList');
    const filteredCount = () => document.getElementById('filteredCount');
    const prevBtn = () => document.getElementById('prevBtn');
    const nextBtn = () => document.getElementById('nextBtn');

    function loadIssues(issues){
      if(!Array.isArray(issues)) issues = [];
      state.issues = issues.slice(); // keep copy
      // build rules set
      const rules = new Set(issues.map(i=>i.rule).filter(Boolean));
      // initialize enabledRules if empty -> full select
      if(state.enabledRules.size === 0){
        rules.forEach(r=>state.enabledRules.add(r));
      }
      renderRuleCheckboxes(Array.from(rules).sort());
      attachFilterControls();
      recalcFiltered();
    }

    function renderRuleCheckboxes(ruleList){
      const rc = rulesContainer();
      rc.innerHTML = '';
      ruleList.forEach(rule=>{
        const id = 'rule_' + btoa(unescape(encodeURIComponent(rule))).replace(/=+$/,'');
        const div = document.createElement('div');
        const cb = document.createElement('input');
        cb.type = 'checkbox'; cb.id = id; cb.checked = state.enabledRules.has(rule);
        cb.addEventListener('change', ()=>{
          if(cb.checked) state.enabledRules.add(rule); else state.enabledRules.delete(rule);
          onFilterChange();
        });
        const label = document.createElement('label');
        label.htmlFor = id; label.textContent = rule;
        div.appendChild(cb); div.appendChild(label);
        rc.appendChild(div);
      });
    }

    function attachFilterControls(){
      const err = document.getElementById('filterErrors');
      const warn = document.getElementById('filterWarnings');
      if(err && !err._attached){
        err.addEventListener('change', ()=>{ state.showErrors = err.checked; onFilterChange(); });
        err._attached = true;
      }
      if(warn && !warn._attached){
        warn.addEventListener('change', ()=>{ state.showWarnings = warn.checked; onFilterChange(); });
        warn._attached = true;
      }
      if(!prevBtn()._attached){
        prevBtn().addEventListener('click', ()=> moveActive(-1)); prevBtn()._attached = true;
      }
      if(!nextBtn()._attached){
        nextBtn().addEventListener('click', ()=> moveActive(1)); nextBtn()._attached = true;
      }
    }

    function onFilterChange(){
      recalcFiltered();
    }

    function recalcFiltered(){
      const enabled = state.enabledRules;
      state.filteredIssues = state.issues.filter(issue => {
        if(!issue || typeof issue !== 'object') return false;
        const lvl = issue.level;
        if(lvl === 'error' && !state.showErrors) return false;
        if(lvl === 'warning' && !state.showWarnings) return false;
        if(!enabled.has(issue.rule)) return false;
        return true;
      });
      state.activeIndex = 0;
      updateUI();
    }

    function updateUI(){
      filteredCount().textContent = `${state.filteredIssues.length} issues`;
      renderIssueList();
      reapplyHighlights();
      updateNavButtons();
      // activate first
      if(state.filteredIssues.length>0) setActiveIndex(0);
    }

    function renderIssueList(){
      const list = issueList();
      list.innerHTML = '';
      if(state.filteredIssues.length === 0){
        const p = document.createElement('div'); p.textContent = '該当するエラーはありません'; p.className='muted'; list.appendChild(p); return;
      }
      state.filteredIssues.forEach((issue, idx)=>{
        const div = document.createElement('div');
        div.className = 'issue-item';
        const lvl = issue.level || '?';
        const rule = issue.rule || '?';
        const row = issue.row || '?';
        const col = issue.column || '?';
        div.innerHTML = `<strong>[${lvl}] ${rule}</strong><div class="muted">Row ${row} • Col ${col}</div>`;
        if(idx === state.activeIndex) div.style.background = '#eef6ff';
        div.addEventListener('click', ()=> setActiveIndex(idx));
        list.appendChild(div);
      });
    }

    function updateNavButtons(){
      const len = state.filteredIssues.length;
      prevBtn().disabled = len === 0 || state.activeIndex <= 0;
      nextBtn().disabled = len === 0 || state.activeIndex >= len-1;
    }

    function setActiveIndex(i){
      if(state.filteredIssues.length === 0) return;
      state.activeIndex = Math.max(0, Math.min(i, state.filteredIssues.length-1));
      // re-render issue list to show active
      renderIssueList();
      // clear previous cell-active
      document.querySelectorAll('.cell-active').forEach(n=>n.classList.remove('cell-active'));
      const issue = state.filteredIssues[state.activeIndex];
      if(!issue) return;
      const sel = `[data-row="${issue.row}"][data-col-name="${cssEscape(issue.column)}"]`;
      const cell = document.querySelector(sel);
      if(cell){
        cell.classList.add('cell-active');
        cell.scrollIntoView({behavior:'smooth', block:'center', inline:'center'});
      } else {
        // unresolved mapping: notify in console
        console.warn('No matching cell for issue', issue);
      }
      updateNavButtons();
    }

    function moveActive(delta){
      if(state.filteredIssues.length === 0) return;
      setActiveIndex(state.activeIndex + delta);
    }

    // apply highlights based on filteredIssues but do not re-render sheet
    function reapplyHighlights(){
      // clear classes
      document.querySelectorAll('.cell-error, .cell-warning, .cell-active').forEach(n=>{
        n.classList.remove('cell-error'); n.classList.remove('cell-warning'); n.classList.remove('cell-active');
      });

      // group by cell
      const byCell = new Map();
      state.filteredIssues.forEach(issue => {
        const key = `${issue.row}||${issue.column}`;
        if(!byCell.has(key)) byCell.set(key, []);
        byCell.get(key).push(issue);
      });

      byCell.forEach((issues, key)=>{
        const [row, column] = key.split('||');
        // decide highest severity
        let hasError = issues.some(i=>i.level==='error');
        let hasWarn = issues.some(i=>i.level==='warning');
        const sel = `[data-row="${row}"][data-col-name="${cssEscape(column)}"]`;
        const cell = document.querySelector(sel);
        if(cell){
          if(hasError) cell.classList.add('cell-error');
          else if(hasWarn) cell.classList.add('cell-warning');
        } else {
          // unresolved mappings are left unhighlighted but logged
          console.warn('Unresolved issue mapping (no cell):', {row, column, issues});
        }
      });
    }

    // helper to escape CSS attr selector for col names that may contain spaces/quotes
    function cssEscape(s){
      if(typeof s !== 'string') return '';
      return s.replace(/"/g,'\\"').replace(/\\/g,'\\\\');
    }

    return {
      loadIssues,
      reapplyHighlights,
      getState: ()=> JSON.parse(JSON.stringify({
        showErrors: state.showErrors,
        showWarnings: state.showWarnings,
        enabledRules: Array.from(state.enabledRules),
        filteredIssues: state.filteredIssues.slice(),
        activeIndex: state.activeIndex,
      })),
    };
  })();

  // expose globals
  window.ExcelViewer = ExcelViewer;
  window.ValidationHighlighter = ValidationHighlighter;

})();
