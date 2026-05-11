"use strict";

(function () {
  const form = document.getElementById("chat-form");
  const input = document.getElementById("message-input");
  const submitButton = document.getElementById("submit-button");
  const formStatus = document.getElementById("form-status");
  const messageList = document.getElementById("message-list");

  let activeSource = null;

  form.addEventListener("submit", async (event) => {
    event.preventDefault();

    const message = input.value.trim();
    if (!message) {
      updateFormState("请输入任务内容。", false);
      input.focus();
      return;
    }

    if (activeSource) {
      activeSource.close();
      activeSource = null;
    }

    setSubmitting(true);
    updateFormState("正在创建任务...", true);
    appendUserMessage(message);

    try {
      const response = await fetch("/api/chat", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ message }),
      });

      if (!response.ok) {
        throw new Error("任务创建失败");
      }

      const payload = await response.json();
      if (!payload.task_id) {
        throw new Error("响应缺少 task_id");
      }

      updateFormState(`任务已创建：${payload.task_id}`, true);
      openStream(payload.task_id);
    } catch (error) {
      setSubmitting(false);
      appendAssistantMessage({
        title: "Request Error",
        body: getErrorMessage(error),
        tone: "error",
      });
      updateFormState("任务创建失败。", false);
    }
  });

  function openStream(taskId) {
    const source = new EventSource(`/api/chat/${encodeURIComponent(taskId)}/stream`);
    activeSource = source;

    source.onmessage = (event) => {
      const payload = parsePayload(event.data);
      if (!payload) {
        return;
      }

      renderPayload(payload);

      if (isTerminalPayload(payload)) {
        finalizeStream();
      }
    };

    source.onerror = () => {
      if (activeSource !== source) {
        return;
      }

      appendAssistantMessage({
        title: "Stream Error",
        body: "事件流已中断，请稍后重试。",
        tone: "error",
      });
      updateFormState("事件流中断。", false);
      finalizeStream();
    };
  }

  function renderPayload(payload) {
    const type = payload.type;

    if (type === "status") {
      appendAssistantMessage({
        title: "Status",
        body: payload.message || "任务状态已更新。",
        tone: "status",
      });
      updateFormState(payload.message || "任务进行中...", true);
      return;
    }

    if (type === "item") {
      const lines = [];
      if (payload.asin) {
        lines.push(`ASIN: ${payload.asin}`);
      }
      if (payload.title) {
        lines.push(`标题: ${payload.title}`);
      }

      const itemMessage = appendAssistantMessage({
        title: "Item Complete",
        body: lines.join("\n") || "单个竞品分析已完成。",
        tone: "item",
      });

      if (payload.row && typeof payload.row === "object") {
        itemMessage.appendChild(buildKeyValueList(payload.row));
      }

      updateFormState("已收到单项分析结果。", true);
      return;
    }

    if (type === "result") {
      const resultMessage = appendAssistantMessage({
        title: "Result",
        body: payload.summary || "任务已完成。",
        tone: "result",
      });

      if (payload.download_url) {
        resultMessage.appendChild(buildDownloadLink(payload.download_url, payload.filename));
      }

      if (Array.isArray(payload.preview_columns) && Array.isArray(payload.preview_rows)) {
        resultMessage.appendChild(buildPreviewTable(payload.preview_columns, payload.preview_rows));
      }

      updateFormState(payload.summary || "任务已完成。", false);
      return;
    }

    if (type === "error") {
      appendAssistantMessage({
        title: "Error",
        body: payload.message || "任务执行失败。",
        tone: "error",
      });
      updateFormState(payload.message || "任务执行失败。", false);
      return;
    }

    appendAssistantMessage({
      title: "Message",
      body: JSON.stringify(payload),
      tone: "status",
    });
  }

  function appendUserMessage(text) {
    appendMessage({
      role: "user",
      title: "You",
      body: text,
      tone: "user",
    });
  }

  function appendAssistantMessage({ title, body, tone }) {
    return appendMessage({
      role: "assistant",
      title,
      body,
      tone,
    });
  }

  function appendMessage({ role, title, body, tone }) {
    const item = document.createElement("li");
    item.className = `message ${role} ${tone || ""}`.trim();

    const card = document.createElement("article");
    card.className = "message-card";

    const meta = document.createElement("div");
    meta.className = "message-meta";

    const roleBadge = document.createElement("span");
    roleBadge.className = "message-role";
    roleBadge.textContent = role === "user" ? "User" : "Assistant";

    const titleNode = document.createElement("h3");
    titleNode.className = "message-title";
    titleNode.textContent = title;

    meta.appendChild(roleBadge);
    meta.appendChild(titleNode);

    const bodyNode = document.createElement("p");
    bodyNode.className = "message-body";
    bodyNode.textContent = body;

    card.appendChild(meta);
    card.appendChild(bodyNode);
    item.appendChild(card);
    messageList.appendChild(item);

    item.scrollIntoView({ behavior: "smooth", block: "end" });
    return card;
  }

  function buildDownloadLink(url, filename) {
    const wrapper = document.createElement("p");
    wrapper.className = "download-wrap";

    const link = document.createElement("a");
    link.className = "download-link";
    link.href = url;
    link.textContent = filename ? `下载 ${filename}` : "下载 CSV";

    wrapper.appendChild(link);
    return wrapper;
  }

  function buildPreviewTable(columns, rows) {
    const section = document.createElement("section");
    section.className = "preview-section";

    const heading = document.createElement("h4");
    heading.className = "preview-title";
    heading.textContent = "CSV Preview";
    section.appendChild(heading);

    const scroller = document.createElement("div");
    scroller.className = "table-scroller";

    const table = document.createElement("table");
    table.className = "preview-table";

    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    columns.forEach((column) => {
      const cell = document.createElement("th");
      cell.scope = "col";
      cell.textContent = String(column);
      headRow.appendChild(cell);
    });
    thead.appendChild(headRow);

    const tbody = document.createElement("tbody");
    rows.forEach((row) => {
      const rowNode = document.createElement("tr");
      row.forEach((value) => {
        const cell = document.createElement("td");
        cell.textContent = value == null ? "" : String(value);
        rowNode.appendChild(cell);
      });
      tbody.appendChild(rowNode);
    });

    table.appendChild(thead);
    table.appendChild(tbody);
    scroller.appendChild(table);
    section.appendChild(scroller);

    return section;
  }

  function buildKeyValueList(row) {
    const fields = ["品牌", "ASIN", "商品标题", "价格", "评分", "评论数", "竞品定位"];
    const list = document.createElement("dl");
    list.className = "row-summary";

    fields.forEach((field) => {
      if (!(field in row)) {
        return;
      }

      const term = document.createElement("dt");
      term.textContent = field;

      const detail = document.createElement("dd");
      detail.textContent = row[field] == null ? "" : String(row[field]);

      list.appendChild(term);
      list.appendChild(detail);
    });

    return list;
  }

  function parsePayload(raw) {
    try {
      return JSON.parse(raw);
    } catch (_error) {
      appendAssistantMessage({
        title: "Parse Error",
        body: "收到无法解析的事件数据。",
        tone: "error",
      });
      return null;
    }
  }

  function finalizeStream() {
    if (activeSource) {
      activeSource.close();
      activeSource = null;
    }
    setSubmitting(false);
  }

  function isTerminalPayload(payload) {
    return payload.type === "result" || payload.type === "error";
  }

  function setSubmitting(isSubmitting) {
    submitButton.disabled = isSubmitting;
    input.disabled = isSubmitting;
  }

  function updateFormState(message, isBusy) {
    formStatus.textContent = message;
    formStatus.dataset.busy = isBusy ? "true" : "false";
  }

  function getErrorMessage(error) {
    if (error instanceof Error && error.message) {
      return error.message;
    }
    return "发生未知错误。";
  }
})();
