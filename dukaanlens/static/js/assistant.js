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

  if (reply.suggestions && reply.suggestions.length) addChips(bubble, reply.suggestions);
  log.scrollTop = log.scrollHeight;
}

async function ask(message) {
  addBubble("user").textContent = message;
  try {
    const response = await fetch(window.ASK_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": window.CSRF_TOKEN },
      body: JSON.stringify({ message }),
    });
    if (!response.ok) throw new Error("Server said " + response.status);
    renderReply(await response.json());
  } catch (err) {
    addBubble("bot").textContent = "Something went wrong. Please try again. (" + err.message + ")";
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
