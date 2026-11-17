const bookInput = document.getElementById("book");
const pdfInput = document.getElementById("pdf");
const statusLine = document.getElementById("status");
const pageList = document.getElementById("page-list");
const editor = document.getElementById("editor");
const jsonPane = document.getElementById("json");
const rules = document.getElementById("rules");
const saveButton = document.getElementById("save");
const pdfFrame = document.getElementById("pdf-frame");
const pdfLink = document.getElementById("pdf-link");

let pages = [];
let currentRel = "";
let previewSerial = 0;
let previewTimer = 0;

document.getElementById("open-form").addEventListener("submit", (event) => {
  event.preventDefault();
  openBook();
});

saveButton.addEventListener("click", () => saveCurrent());

editor.addEventListener("input", () => {
  window.clearTimeout(previewTimer);
  previewTimer = window.setTimeout(() => refreshPreview(), 400);
});

document.addEventListener("keydown", (event) => {
  if ((event.ctrlKey || event.metaKey) && event.key === "s") {
    event.preventDefault();
    saveCurrent();
  }
});

async function openBook() {
  setStatus("正在打开…", "");
  const payload = await postJson("/api/open", {
    book_dir: bookInput.value.trim(),
    pdf_path: pdfInput.value.trim(),
  });
  if (!payload.ok) {
    showFailure(payload);
    return;
  }
  pages = payload.pages;
  renderList();
  setStatus(`已打开 ${pages.length} 页。保存时只写另存稿。`, "ok");
  if (pages.length) await selectPage(pages[0].rel);
}

async function selectPage(rel) {
  currentRel = rel;
  renderList();
  const payload = await getJson("/api/page?rel=" + encodeURIComponent(rel));
  if (!payload.ok) {
    showFailure(payload);
    return;
  }
  editor.disabled = false;
  saveButton.disabled = false;
  editor.value = payload.markdown;
  const source = payload.loaded_from === "reviewed" ? "正在继续改已另存的稿" : "正在从原始 Markdown 开始";
  rules.textContent = `${payload.label}：原 JSON 有 ${payload.block_count} 块。${source}。一块时整页写入。多块时，块与块之间单独一行写 ---，段数必须相同，否则不写入。`;
  showPreview(payload.preview, payload.preview_error);
  const pageNo = payload.page_no || 1;
  const frameUrl = "/pdf?page=" + pageNo + "#page=" + pageNo;
  pdfFrame.src = frameUrl;
  pdfLink.href = frameUrl;
  if (!payload.page_no) {
    setStatus("这一页的路径里没有 page_0001 这样的页码，PDF 先停在第 1 页。", "ok");
  }
}

function renderList() {
  pageList.replaceChildren();
  for (const page of pages) {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = page.has_reviewed ? page.label + " · 已另存" : page.label;
    if (page.rel === currentRel) button.setAttribute("aria-current", "true");
    button.addEventListener("click", () => selectPage(page.rel));
    pageList.appendChild(button);
  }
}

async function refreshPreview() {
  if (!currentRel) return;
  const serial = ++previewSerial;
  const payload = await postJson("/api/preview", {
    rel: currentRel,
    markdown: editor.value,
  });
  if (serial !== previewSerial) return;
  if (!payload.ok) {
    showPreview("", payload);
    return;
  }
  showPreview(payload.preview, null);
}

function showPreview(preview, error) {
  if (error) {
    jsonPane.dataset.state = "error";
    jsonPane.textContent = error.message + (error.request_id ? "\n请求编号 " + error.request_id : "");
    return;
  }
  jsonPane.dataset.state = "ok";
  jsonPane.textContent = preview || "";
}

async function saveCurrent() {
  if (!currentRel || saveButton.disabled) return;
  saveButton.disabled = true;
  setStatus("正在另存…", "");
  const payload = await postJson("/api/save", {
    rel: currentRel,
    markdown: editor.value,
  });
  saveButton.disabled = false;
  if (!payload.ok) {
    showFailure(payload);
    showPreview("", payload);
    return;
  }
  const page = pages.find((item) => item.rel === currentRel);
  if (page) page.has_reviewed = true;
  renderList();
  const backup = payload.backed_up ? "上一份另存稿已备份。" : "";
  setStatus(payload.message + backup + " 请求编号 " + payload.request_id, "ok");
  showPreview(jsonPane.dataset.state === "error" ? "" : jsonPane.textContent, null);
  await refreshPreview();
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
