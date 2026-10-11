// Chat page: sends the question to /assistant/ask and shows the answer.
const log = document.getElementById("chat-log");
const form = document.getElementById("chat-form");
const input = document.getElementById("chat-message");

function addBubble(kind) {
  const div = document.createElement("div");
  div.className = "bubble " + kind;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  return div;
}

function formatCell(value) {
  return typeof value === "number" ? value.toLocaleString("en-IN", { maximumFractionDigits: 2 }) : String(value ?? "");
}

function addChips(container, suggestions) {
  const chips = document.createElement("div");
  chips.className = "chips mt-2";
  suggestions.forEach((text) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "btn btn-sm btn-outline-primary chip";
    button.textContent = text;
    chips.appendChild(button);
  });
  container.appendChild(chips);
}

function renderReply(reply) {
  const bubble = addBubble("bot");
  const answer = document.createElement("div");
  answer.textContent = reply.answer;
  bubble.appendChild(answer);

  if (reply.columns && reply.columns.length && reply.rows && reply.rows.length) {
    const wrap = document.createElement("div");
    wrap.className = "table-responsive mt-2";
    const table = document.createElement("table");
    table.className = "table table-sm table-bordered mb-0";
    const head = table.createTHead().insertRow();
    reply.columns.forEach((c) => {
      const th = document.createElement("th");
      th.textContent = c;
      head.appendChild(th);
    });
    const body = table.createTBody();
    reply.rows.forEach((row) => {
      const tr = body.insertRow();
      row.forEach((cell) => { tr.insertCell().textContent = formatCell(cell); });
    });
    wrap.appendChild(table);
    bubble.appendChild(wrap);
  }

  if (reply.sql) {
    const details = document.createElement("details");
    details.className = "mt-2";
    const summary = document.createElement("summary");
    summary.textContent = "Show SQL used";
    const pre = document.createElement("pre");
    pre.className = "mt-2 mb-1";
    pre.textContent = reply.sql;
    const params = document.createElement("small");
    params.className = "text-muted";
    params.textContent = "Parameters: " + JSON.stringify(reply.params);
    details.append(summary, pre, params);
    bubble.appendChild(details);
  }

  if (reply.notes && reply.notes.length) {
    const how = document.createElement("div");
    how.className = "small text-muted mt-2";
    how.textContent = "How I read it: " + reply.notes.join(" · ");
    bubble.appendChild(how);
  }

  if (reply.suggestions && reply.suggestions.length) addChips(bubble, reply.suggestions);
  log.scrollTop = log.scrollHeight;
}

const sourceSelect = document.getElementById("source");

function welcome() {
  log.textContent = "";
  const bubble = addBubble("bot");
  const table = window.TABLES.find((t) => String(t.id) === sourceSelect.value);
  const intro = document.createElement("div");
  if (table) {
    intro.textContent = "Ask about the uploaded table '" + table.name + "'. Columns: " +
      table.columns.join(", ") + ". Try:";
    bubble.appendChild(intro);
    addChips(bubble, table.suggestions);
  } else {
    intro.textContent = "Hi! Ask me something like:";
    bubble.appendChild(intro);
    addChips(bubble, window.RECORD_SUGGESTIONS);
  }
}
sourceSelect.addEventListener("change", () => { history = []; welcome(); });
welcome();

let history = [];   // last few Q&A pairs, so follow-up answers have context

async function ask(message) {
  addBubble("user").textContent = message;
  const thinking = addBubble("bot");
  thinking.textContent = "Thinking...";
  try {
    const response = await fetch(window.ASK_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": window.CSRF_TOKEN },
      body: JSON.stringify({ message, source: sourceSelect.value, history }),
    });
    if (!response.ok) throw new Error("Server said " + response.status);
    const reply = await response.json();
    thinking.remove();
    renderReply(reply);
    history = history.concat([{ q: message, a: reply.answer }]).slice(-3);
  } catch (err) {
    thinking.textContent = "Something went wrong. Please try again. (" + err.message + ")";
  }
}

form.addEventListener("submit", (event) => {
  event.preventDefault();
  const message = input.value.trim();
  if (!message) return;
  input.value = "";
  ask(message);
});

log.addEventListener("click", (event) => {
  if (event.target.classList.contains("chip")) ask(event.target.textContent);
});
