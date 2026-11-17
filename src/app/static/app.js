const bookName = document.getElementById("book-name");
const pdfName = document.getElementById("pdf-name");
const statusLine = document.getElementById("status");
const pageSelect = document.getElementById("page-select");
const prevButton = document.getElementById("prev-page");
const nextButton = document.getElementById("next-page");
const rendered = document.getElementById("rendered");
const jsonPane = document.getElementById("json");
const drafts = document.getElementById("drafts");
const draftHeading = document.getElementById("draft-heading");
const pageRoleSelect = document.getElementById("page-role");
const rules = document.getElementById("rules");
const saveButton = document.getElementById("save");
const exportButton = document.getElementById("export");
const pdfFrame = document.getElementById("pdf-frame");
const pdfLink = document.getElementById("pdf-link");

const SYMBOLS = {
  pi: "π", pm: "±", times: "×", cdot: "·", div: "÷",
  leq: "≤", geq: "≥", neq: "≠", approx: "≈", infty: "∞",
  alpha: "α", beta: "β", gamma: "γ", theta: "θ", degree: "°",
  ldots: "…", cdots: "⋯", quad: " ", qquad: "  ",
};

let bookPath = "";
let pdfPath = "";
let pages = [];
let currentRel = "";
let previewSerial = 0;
let jsonTimer = 0;
let saveTimer = 0;
let dirty = false;
let saveChain = Promise.resolve();
let jsonOk = true;
let pageReady = false;
let sourceText = "";
let blocks = [];
let editing = -1;
let editToken = 0;
let typeOverrides = {};
let answerConfirms = {};
const TYPE_OPTIONS = [
  ["unresolved", "待确认"],
  ["single_choice", "单选"],
  ["multiple_choice", "多选"],
  ["fill_blank", "填空"],
  ["solution", "解答"],
];

document.getElementById("pick-book").addEventListener("click", () => choose("book"));
document.getElementById("pick-pdf").addEventListener("click", () => choose("pdf"));
saveButton.addEventListener("click", () => enqueueSave(true));
exportButton.addEventListener("click", () => exportCurrent());
pageRoleSelect.addEventListener("change", () => {
  answerConfirms = {};
  typeOverrides = {};
  noteEdit();
});
prevButton.addEventListener("click", () => step(-1));
nextButton.addEventListener("click", () => step(1));
pageSelect.addEventListener("change", () => goTo(pageSelect.value));

document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "s") {
    event.preventDefault();
    enqueueSave(true);
  }
});

async function choose(kind) {
  setStatus("请在弹出的窗口里选择。", "");
  const payload = await postJson("/api/pick", {kind});
  if (!payload.ok) {
    showFailure(payload);
    return;
  }
  if (payload.cancelled) {
    setStatus("已取消选择。", "");
    return;
  }
  if (kind === "book") {
    bookPath = payload.path;
    bookName.textContent = baseName(payload.path);
    bookName.title = payload.path;
  } else {
    pdfPath = payload.path;
    pdfName.textContent = baseName(payload.path);
    pdfName.title = payload.path;
  }
  if (bookPath && pdfPath) await openBook();
}

async function openBook() {
  setStatus("正在打开…", "");
  const payload = await postJson("/api/open", {book_dir: bookPath, pdf_path: pdfPath});
  if (!payload.ok) {
    showFailure(payload);
    return;
  }
  pages = payload.pages;
  renderPager();
  setStatus(`已打开 ${pages.length} 页。改完会自动保存。`, "ok");
  if (pages.length) await selectPage(pages[0].rel);
}

async function step(delta) {
  const index = pages.findIndex((page) => page.rel === currentRel);
  const next = pages[index + delta];
  if (next) await goTo(next.rel);
}

async function goTo(rel) {
  if (!rel || rel === currentRel) return;
  window.clearTimeout(saveTimer);
  await enqueueSave(false);
  await selectPage(rel);
}

async function selectPage(rel) {
  currentRel = rel;
  renderPager();
  const payload = await getJson("/api/page?rel=" + encodeURIComponent(rel));
  if (!payload.ok) {
    showFailure(payload);
    return;
  }
  pageReady = true;
  saveButton.disabled = false;
  exportButton.disabled = false;
  pageRoleSelect.disabled = false;
  pageRoleSelect.value = payload.page_role === "answers" ? "answers" : "questions";
  editToken += 1;
  typeOverrides = {};
  answerConfirms = {};
  (payload.answers || []).forEach((item) => {
    if (item && item.applicable && item.key) answerConfirms[item.key] = true;
  });
  setSource(payload.markdown);
  dirty = false;
  saveButton.textContent = "保存";
  const loadedNote = payload.loaded_from === "reviewed" ? "正在继续改已保存的稿" : "正在从原始 Markdown 开始";
  rules.textContent = `${payload.label}：原 JSON 有 ${payload.block_count} 块。${loadedNote}。点一行即可改。多块时，块与块之间单独一行写 ---。`;
  renderLive();
  renderSide(payload);
  showJson(payload.preview, payload.preview_error);
  jsonOk = !payload.preview_error;
  const pageNo = payload.page_no || 1;
  const frameUrl = "/pdf?page=" + pageNo + "#page=" + pageNo;
  pdfFrame.src = frameUrl;
  pdfLink.href = frameUrl;
}

function renderPager() {
  const index = pages.findIndex((page) => page.rel === currentRel);
  pageSelect.replaceChildren();
  for (const page of pages) {
    const option = document.createElement("option");
    option.value = page.rel;
    option.textContent = page.has_reviewed ? page.label + " · 已保存" : page.label;
    pageSelect.appendChild(option);
  }
  pageSelect.disabled = pages.length === 0;
  if (currentRel) pageSelect.value = currentRel;
  prevButton.disabled = index <= 0;
  nextButton.disabled = index < 0 || index >= pages.length - 1;
}

function setSource(text) {
  sourceText = String(text ?? "");
  blocks = sourceToBlocks(sourceText);
  editing = -1;
}

function sourceToBlocks(text) {
  return String(text ?? "").split("\n").map((line) => ({text: line}));
}

function blocksToSource(items) {
  return items.map((block) => block.text).join("\n");
}

function renderLive() {
  const scroll = rendered.scrollTop;
  rendered.replaceChildren();
  blocks.forEach((block, index) => {
    if (index === editing) {
      const box = document.createElement("textarea");
      box.className = "block-edit";
      box.setAttribute("aria-label", "编辑这一行");
      box.spellcheck = false;
      box.value = block.text;
      box.rows = 1;
      box.addEventListener("input", () => {
        block.text = box.value;
        fitLine(box);
        noteEdit();
      });
      box.addEventListener("keydown", (event) => {
        if (event.key === "Escape" || (event.key === "Enter" && !event.shiftKey)) {
          event.preventDefault();
          box.blur();
        }
      });
      box.addEventListener("blur", () => {
        const token = editToken;
        const rel = currentRel;
        window.setTimeout(() => {
          if (token !== editToken || rel !== currentRel) return;
          if (rendered.contains(document.activeElement)) return;
          editing = -1;
          sourceText = blocksToSource(blocks);
          blocks = sourceToBlocks(sourceText);
          renderLive();
        }, 0);
      });
      rendered.appendChild(box);
      fitLine(box);
      box.focus();
      return;
    }
    const row = document.createElement("div");
    row.className = block.text.trim() === "" ? "block blank" : "block";
    row.innerHTML = block.text.trim() === "" ? "" : renderMarkdown(block.text);
    row.addEventListener("mousedown", (event) => {
      event.preventDefault();
      openBlock(index);
    });
    rendered.appendChild(row);
  });
  rendered.scrollTop = scroll;
}

function openBlock(index) {
  editToken += 1;
  sourceText = blocksToSource(blocks);
  editing = index;
  renderLive();
}

function fitLine(box) {
  box.style.height = "auto";
  box.style.height = box.scrollHeight + "px";
}

function noteEdit() {
  sourceText = blocksToSource(blocks);
  dirty = true;
  saveButton.textContent = "保存";
  window.clearTimeout(jsonTimer);
  window.clearTimeout(saveTimer);
  jsonTimer = window.setTimeout(() => refreshJson(), 300);
  saveTimer = window.setTimeout(() => enqueueSave(false), 800);
}

async function refreshJson() {
  if (!currentRel) return;
  const serial = ++previewSerial;
  const payload = await postJson("/api/preview", {
    rel: currentRel,
    markdown: sourceText,
    page_role: pageRole(),
    answer_confirms: confirmList(),
  });
  if (serial !== previewSerial) return;
  if (!payload.ok) {
    jsonOk = false;
    showJson("", payload);
    return;
  }
  jsonOk = true;
  showJson(payload.preview, null);
  renderSide(payload);
  if (dirty) {
    window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(() => enqueueSave(false), 400);
  }
}

function pageRole() {
  return pageRoleSelect.value === "answers" ? "answers" : "questions";
}

function confirmList() {
  return Object.keys(answerConfirms);
}

function renderSide(payload) {
  if (pageRole() === "answers") renderAnswers(payload.answers || []);
  else renderDrafts(payload.questions);
}

function renderAnswers(files) {
  if (!drafts) return;
  draftHeading.textContent = "参考答案";
  drafts.replaceChildren();
  const note = document.createElement("p");
  note.className = "draft-note";
  if (!files.length) {
    note.textContent = "还没有答案。题型标题和题号要和题目页一致，例如「一. 选择题」下面写「1. A」。";
    drafts.appendChild(note);
    return;
  }
  note.textContent = `扫描答案 ${files.length} 条。同一题只勾一条。勾选后仍不是发布，也还没有写入数据库。`;
  drafts.appendChild(note);
  files.forEach((item) => {
    const card = document.createElement("article");
    card.className = "draft";
    const title = document.createElement("strong");
    title.textContent = `${item.question_key} · ${answerStatus(item.status)}`;
    const body = document.createElement("p");
    body.textContent = answerBody(item);
    const label = document.createElement("label");
    const box = document.createElement("input");
    box.type = "checkbox";
    box.checked = Boolean(answerConfirms[item.key]);
    box.setAttribute("aria-label", `采用 ${item.question_key} 的扫描答案`);
    box.addEventListener("change", () => {
      if (box.checked) {
        files.forEach((other) => {
          if (other.question_key === item.question_key) delete answerConfirms[other.key];
        });
        answerConfirms[item.key] = true;
      } else {
        delete answerConfirms[item.key];
      }
      noteEdit();
    });
    label.append(box, document.createTextNode("采用这条扫描答案"));
    card.append(title, body, label);
    drafts.appendChild(card);
  });
}

function answerStatus(status) {
  if (status === "confirmed") return "已确认";
  if (status === "needs_confirm") return "待确认";
  if (status === "disputed") return "有分歧";
  return "候选";
}

function answerBody(item) {
  const lines = [];
  const main = partsText(item.content);
  if (main) lines.push(main);
  (item.parts || []).forEach((part) => {
    const mark = part.sub_key ? `(${part.sub_key}) ` : "";
    const role = part.role === "step" ? "步骤 " : "";
    lines.push(mark + role + partsText(part.content));
  });
  return lines.join("  ") || item.key;
}

function renderDrafts(split) {
  if (!drafts) return;
  draftHeading.textContent = "题目草稿";
  drafts.replaceChildren();
  if (!split) return;
  const note = document.createElement("p");
  note.className = "draft-note";
  if (!split.ok) {
    note.textContent = split.reason || "这一页没有拆成草稿。";
    drafts.appendChild(note);
    return;
  }
  const counts = countTypes(split.questions);
  note.textContent = `导读不建题。草稿 ${split.questions.length} 道：${counts}`;
  drafts.appendChild(note);
  split.questions.forEach((question) => {
    const card = document.createElement("article");
    card.className = "draft";
    const head = document.createElement("div");
    head.className = "draft-head";
    const title = document.createElement("strong");
    const shown = typeOverrides[question.key] || question.type;
    title.textContent = `第 ${question.number} 题 · ${statusLabel(question, shown)}`;
    const select = document.createElement("select");
    select.setAttribute("aria-label", `第 ${question.number} 题题型`);
    TYPE_OPTIONS.forEach(([value, label]) => {
      const option = document.createElement("option");
      option.value = value;
      option.textContent = label;
      select.appendChild(option);
    });
    select.value = TYPE_OPTIONS.some(([value]) => value === shown) ? shown : "unresolved";
    select.addEventListener("change", () => {
      if (select.value === "unresolved") delete typeOverrides[question.key];
      else typeOverrides[question.key] = select.value;
      title.textContent = `第 ${question.number} 题 · ${select.value === question.type ? statusLabel(question, select.value) : "已确认"}`;
      noteEdit();
    });
    head.append(title, select);
    const stem = document.createElement("p");
    stem.textContent = partsText(question.stem);
    card.append(head, stem);
    if (question.options && question.options.length) {
      const options = document.createElement("p");
      options.textContent = question.options.map((item) => item.key + ". " + partsText(item.content)).join("  ");
      card.append(options);
    }
    if (question.subquestions && question.subquestions.length) {
      const subs = document.createElement("p");
      subs.textContent = question.subquestions.map((item) => `(${item.number}) ${partsText(item.stem)}`).join("  ");
      card.append(subs);
    }
    drafts.appendChild(card);
  });
}

function countTypes(questions) {
  const names = {single_choice: "单选", multiple_choice: "多选", fill_blank: "填空", solution: "解答", unresolved: "待确认"};
  const totals = {};
  questions.forEach((question) => {
    const key = typeOverrides[question.key] || question.type;
    totals[key] = (totals[key] || 0) + 1;
  });
  return Object.entries(totals).map(([key, count]) => `${names[key] || key} ${count}`).join("，");
}

function statusLabel(question, shown) {
  if (typeOverrides[question.key]) return "已确认";
  if (question.status === "candidate") return TYPE_OPTIONS.find(([value]) => value === shown)?.[1] + " · 候选" || "候选";
  return "待确认";
}

function partsText(parts) {
  return (parts || []).map((part) => part.type === "math" ? "$" + part.latex + "$" : part.value).join("");
}

function showJson(preview, error) {
  if (error) {
    jsonPane.dataset.state = "error";
    jsonPane.textContent = error.message || "";
    return;
  }
  jsonPane.dataset.state = "ok";
  jsonPane.textContent = preview || "";
}

function enqueueSave(manual) {
  saveChain = saveChain.then(() => saveCurrent(manual)).catch(() => {});
  return saveChain;
}

async function saveCurrent(manual) {
  if (!currentRel || !pageReady) return;
  if (!manual && !dirty) return;
  if (!jsonOk) {
    if (manual) setStatus("这一页的块数对不上，没有保存。", "error");
    return;
  }
  sourceText = blocksToSource(blocks);
  const snapshot = sourceText;
  const payload = await postJson("/api/save", {
    rel: currentRel,
    markdown: snapshot,
    backup: manual,
    type_overrides: typeOverrides,
    page_role: pageRole(),
    answer_confirms: confirmList(),
  });
  if (!payload.ok) {
    showFailure(payload);
    return;
  }
  if (sourceText === snapshot) {
    dirty = false;
    saveButton.textContent = "保存";
  } else {
    window.clearTimeout(saveTimer);
    saveTimer = window.setTimeout(() => enqueueSave(false), 800);
  }
  const page = pages.find((item) => item.rel === currentRel);
  if (page) page.has_reviewed = true;
  renderPager();
  const backup = payload.backed_up ? "上一份已备份。" : "";
  setStatus(payload.message + backup, "ok");
}

async function exportCurrent() {
  if (!currentRel) return;
  setStatus("请在弹出的窗口里选择导出文件夹。", "");
  const picked = await postJson("/api/pick", {kind: "export"});
  if (!picked.ok) {
    showFailure(picked);
    return;
  }
  if (picked.cancelled) {
    setStatus("已取消导出。", "");
    return;
  }
  const payload = await postJson("/api/export", {
    rel: currentRel,
    markdown: sourceText,
    export_dir: picked.path,
    page_role: pageRole(),
    answer_confirms: confirmList(),
    type_overrides: typeOverrides,
  });
  if (!payload.ok) {
    showFailure(payload);
    return;
  }
  const backup = payload.backed_up ? "该文件夹里的旧文件已备份。" : "";
  setStatus(payload.message + "位置：" + baseName(picked.path) + "。" + backup, "ok");
}

function showFailure(payload) {
  const code = payload.error_code ? "错误编号 " + payload.error_code + "。" : "";
  const request = payload.request_id ? "请求编号 " + payload.request_id + "。日志在 logs/app.jsonl。" : "";
  setStatus(code + (payload.message || "没有完成。") + request, "error");
}

function setStatus(text, state) {
  statusLine.textContent = text;
  statusLine.dataset.state = state || "";
}

function baseName(path) {
  const parts = String(path).split(/[\\/]/);
  return parts[parts.length - 1] || path;
}

function renderMarkdown(source) {
  const pieces = [];
  let index = 0;
  const text = String(source || "");
  while (index < text.length) {
    if (text.startsWith("$$", index)) {
      const end = text.indexOf("$$", index + 2);
      if (end >= 0) {
        pieces.push(`<span class="math display">${renderTex(text.slice(index + 2, end))}</span>`);
        index = end + 2;
        continue;
      }
    }
    if (text[index] === "$") {
      const end = text.indexOf("$", index + 1);
      if (end > index + 1) {
        pieces.push(`<span class="math">${renderTex(text.slice(index + 1, end))}</span>`);
        index = end + 1;
        continue;
      }
    }
    const next = text.indexOf("$", index);
    const stop = next < 0 ? text.length : next;
    pieces.push(formatText(text.slice(index, stop)));
    index = stop;
  }
  return pieces.join("");
}

function formatText(text) {
  return text.split("\n").map((line) => {
    const heading = /^(#{1,3})\s+(.*)$/.exec(line);
    if (heading) {
      const level = heading[1].length + 2;
      return `<h${level}>${inline(heading[2])}</h${level}>`;
    }
    if (line.trim() === "---") return "<hr>";
    return inline(line);
  }).join("<br>");
}

function inline(text) {
  return escapeHtml(text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function renderTex(tex) {
  let html = "";
  let index = 0;
  while (index < tex.length) {
    if (tex.startsWith("\\textcircled", index)) {
      index += "\\textcircled".length;
      const arg = readBrace(tex, index);
      index = arg.end;
      html += escapeHtml(circled(arg.body.trim()));
      continue;
    }
    if (tex.startsWith("\\text", index)) {
      index += "\\text".length;
      const arg = readBrace(tex, index);
      index = arg.end;
      html += escapeHtml(arg.body);
      continue;
    }
    if (tex.startsWith("\\frac", index)) {
      index += "\\frac".length;
      const numerator = readBrace(tex, index);
      index = numerator.end;
      const denominator = readBrace(tex, index);
      index = denominator.end;
      html += `<span class="frac"><span class="num">${renderTex(numerator.body)}</span><span class="den">${renderTex(denominator.body)}</span></span>`;
      continue;
    }
    if (tex[index] === "\\") {
      const match = /^\\([a-zA-Z]+)/.exec(tex.slice(index));
      if (match) {
        html += escapeHtml(SYMBOLS[match[1]] || match[1]);
        index += match[0].length;
        continue;
      }
    }
    html += escapeHtml(tex[index]);
    index += 1;
  }
  return html;
}

function readBrace(text, index) {
  while (text[index] === " ") index += 1;
  if (text[index] !== "{") return {body: "", end: index};
  let depth = 0;
  const start = index + 1;
  for (let cursor = index; cursor < text.length; cursor += 1) {
    if (text[cursor] === "{") depth += 1;
    else if (text[cursor] === "}") {
      depth -= 1;
      if (depth === 0) return {body: text.slice(start, cursor), end: cursor + 1};
    }
  }
  return {body: text.slice(start), end: text.length};
}

function circled(value) {
  const number = Number(value);
  if (Number.isInteger(number) && number >= 1 && number <= 20) {
    return String.fromCodePoint(0x2460 + number - 1);
  }
  return "(" + value + ")";
}

function escapeHtml(text) {
  return String(text).replace(/[&<>"']/g, (ch) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[ch]));
}

async function getJson(url) {
  const response = await fetch(url);
  return response.json();
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify(body),
  });
  return response.json();
}
