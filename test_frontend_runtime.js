"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

class FakeElement {
  constructor(tagName, id = null) {
    this.tagName = tagName.toUpperCase();
    this.id = id;
    this.children = [];
    this.listeners = {};
    this.dataset = {};
    this.className = "";
    this.textContent = "";
    this.value = "";
    this.disabled = false;
    this.href = "";
    this.scope = "";
    this.scrollIntoViewCalls = [];
    this.scrollTop = 0;
    this.scrollHeight = 0;
  }

  appendChild(child) {
    this.children.push(child);
    child.parentNode = this;
    this.scrollHeight = this.children.length * 100;
    if (this.parentNode) {
      this.parentNode.scrollHeight = this.scrollHeight;
    }
    return child;
  }

  addEventListener(type, listener) {
    this.listeners[type] = listener;
  }

  scrollIntoView(options) {
    this.scrollIntoViewCalls.push(options || null);
  }
}

class FakeDocument {
  constructor() {
    this.elements = {};
  }

  registerElement(id, tagName) {
    const element = new FakeElement(tagName, id);
    this.elements[id] = element;
    return element;
  }

  getElementById(id) {
    return this.elements[id] || null;
  }

  createElement(tagName) {
    return new FakeElement(tagName);
  }
}

class FakeEventSource {
  static instances = [];

  constructor(url) {
    this.url = url;
    this.readyState = FakeEventSource.OPEN;
    this.closed = false;
    this.onmessage = null;
    this.onerror = null;
    FakeEventSource.instances.push(this);
  }

  close() {
    this.readyState = FakeEventSource.CLOSED;
    this.closed = true;
  }
}

FakeEventSource.CONNECTING = 0;
FakeEventSource.OPEN = 1;
FakeEventSource.CLOSED = 2;

function buildFetch() {
  return async function fetch(url, options = {}) {
    if (url === "/api/sessions" && options.method === "POST") {
      return {
        ok: true,
        async json() {
          return { session_id: "session-1" };
        },
      };
    }

    if (url === "/api/sessions/session-1/messages" && options.method === "POST") {
      return {
        ok: true,
        async json() {
          return { session_id: "session-1", run_id: "run-1" };
        },
      };
    }

    throw new Error(`unexpected fetch request: ${url}`);
  };
}

function buildFetchWithExpiredSessionRetry() {
  let createSessionCount = 0;
  let firstMessageAttempt = true;

  return async function fetch(url, options = {}) {
    if (url === "/api/sessions" && options.method === "POST") {
      createSessionCount += 1;
      return {
        ok: true,
        async json() {
          return { session_id: createSessionCount === 1 ? "session-1" : "session-2" };
        },
      };
    }

    if (url === "/api/sessions/session-1/messages" && options.method === "POST" && firstMessageAttempt) {
      firstMessageAttempt = false;
      return {
        ok: false,
        status: 404,
        async json() {
          return { detail: "Session not found" };
        },
      };
    }

    if (url === "/api/sessions/session-2/messages" && options.method === "POST") {
      return {
        ok: true,
        async json() {
          return { session_id: "session-2", run_id: "run-2" };
        },
      };
    }

    throw new Error(`unexpected fetch request: ${url}`);
  };
}

async function flushMicrotasks() {
  for (let index = 0; index < 6; index += 1) {
    await Promise.resolve();
  }
}

async function loadApp(fetchImpl = buildFetch()) {
  FakeEventSource.instances.length = 0;

  const document = new FakeDocument();
  const form = document.registerElement("chat-form", "form");
  const input = document.registerElement("message-input", "input");
  const submitButton = document.registerElement("submit-button", "button");
  const formStatus = document.registerElement("form-status", "p");
  const conversationPanel = document.registerElement("conversation-panel", "section");
  const messageList = document.registerElement("message-list", "ol");
  const processingIndicator = document.registerElement("processing-indicator", "div");
  const processingText = document.registerElement("processing-text", "p");
  conversationPanel.appendChild(messageList);
  conversationPanel.appendChild(processingIndicator);

  const context = {
    document,
    window: {},
    EventSource: FakeEventSource,
    fetch: fetchImpl,
    console,
    Error,
    JSON,
    encodeURIComponent,
  };
  context.window = context;

  const script = fs.readFileSync(path.join(__dirname, "frontend", "app.js"), "utf-8");
  vm.runInNewContext(script, context, { filename: "frontend/app.js" });
  await flushMicrotasks();

  return {
    form,
    input,
    submitButton,
    formStatus,
    conversationPanel,
    messageList,
    processingIndicator,
    processingText,
  };
}

test("frontend keeps the active run locked through transport errors until done", async () => {
  const { form, input, submitButton, formStatus, messageList } = await loadApp();

  assert.equal(submitButton.disabled, false);
  assert.equal(formStatus.textContent, "会话已创建：session-1");

  input.value = "继续分析";
  await form.listeners.submit({
    preventDefault() {},
  });
  await flushMicrotasks();

  assert.equal(messageList.children.length, 1);
  assert.equal(input.disabled, true);
  assert.equal(submitButton.disabled, true);
  assert.equal(FakeEventSource.instances.length, 1);

  const source = FakeEventSource.instances[0];
  source.onerror();
  await flushMicrotasks();

  assert.equal(source.closed, false);
  assert.equal(input.disabled, true);
  assert.equal(submitButton.disabled, true);
  assert.equal(formStatus.dataset.busy, "true");
  assert.match(formStatus.textContent, /重连|中断/);

  source.onmessage({
    data: JSON.stringify({ type: "done" }),
  });
  await flushMicrotasks();

  assert.equal(source.closed, true);
  assert.equal(input.disabled, false);
  assert.equal(submitButton.disabled, false);
  assert.equal(formStatus.textContent, "等待下一条消息。");
});

test("frontend recreates the session and retries once when the session has expired", async () => {
  const { form, input, submitButton, formStatus } = await loadApp(buildFetchWithExpiredSessionRetry());

  assert.equal(formStatus.textContent, "会话已创建：session-1");

  input.value = "继续分析";
  await form.listeners.submit({
    preventDefault() {},
  });
  await flushMicrotasks();

  assert.equal(FakeEventSource.instances.length, 1);
  assert.equal(FakeEventSource.instances[0].url, "/api/sessions/session-2/runs/run-2/stream");
  assert.equal(input.value, "");
  assert.equal(submitButton.disabled, true);
});

test("frontend scrolls the conversation panel while keeping message cards top-stacked", async () => {
  const { form, input, conversationPanel, messageList } = await loadApp();

  input.value = "继续分析";
  await form.listeners.submit({
    preventDefault() {},
  });
  await flushMicrotasks();

  const source = FakeEventSource.instances[0];
  source.onmessage({
    data: JSON.stringify({ type: "assistant", message: "这是回复" }),
  });
  await flushMicrotasks();

  assert.equal(conversationPanel.scrollTop, conversationPanel.scrollHeight);
  assert.equal(messageList.scrollTop, 0);
  for (const item of messageList.children) {
    assert.equal(item.scrollIntoViewCalls.length, 0);
  }
});

test("frontend shows a single processing indicator for tool status instead of appending a status card", async () => {
  const { form, input, messageList, processingIndicator, processingText } = await loadApp();

  input.value = "继续分析";
  await form.listeners.submit({
    preventDefault() {},
  });
  await flushMicrotasks();

  const source = FakeEventSource.instances[0];
  source.onmessage({
    data: JSON.stringify({ type: "tool_status", message: "正在抓取 Amazon 商品..." }),
  });
  await flushMicrotasks();

  assert.equal(messageList.children.length, 1);
  assert.equal(processingIndicator.hidden, false);
  assert.equal(processingIndicator.dataset.state, "active");
  assert.equal(processingText.textContent, "正在抓取 Amazon 商品...");

  source.onmessage({
    data: JSON.stringify({
      type: "artifact",
      summary: "结果已生成。",
      preview_columns: ["品牌"],
      preview_rows: [["Blackview"]],
    }),
  });
  await flushMicrotasks();

  assert.equal(messageList.children.length, 2);
  assert.equal(processingIndicator.hidden, true);
  assert.equal(processingIndicator.dataset.state, "idle");
});

test("frontend preview cells collapse by default and toggle expansion on click", async () => {
  const { form, input, messageList } = await loadApp();

  input.value = "继续分析";
  await form.listeners.submit({
    preventDefault() {},
  });
  await flushMicrotasks();

  const source = FakeEventSource.instances[0];
  source.onmessage({
    data: JSON.stringify({
      type: "artifact",
      summary: "结果已生成。",
      preview_columns: ["标题", "描述"],
      preview_rows: [["Blackview BV9300", "这是一段很长很长的描述文字，用来测试预览字段默认折叠展示，点击后再展开全部内容。"]],
    }),
  });
  await flushMicrotasks();

  const artifactItem = messageList.children[1];
  const artifactCard = artifactItem.children[0];
  const previewSection = artifactCard.children[2];
  const scroller = previewSection.children[1];
  const table = scroller.children[0];
  const tbody = table.children[1];
  const firstRow = tbody.children[0];
  const descriptionCell = firstRow.children[1];
  const toggle = descriptionCell.children[0];

  assert.equal(toggle.className, "preview-cell-toggle");
  assert.equal(toggle.dataset.expanded, "false");

  toggle.listeners.click();
  assert.equal(toggle.dataset.expanded, "true");

  toggle.listeners.click();
  assert.equal(toggle.dataset.expanded, "false");
});
