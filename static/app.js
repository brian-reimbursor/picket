// Workspace bootstrap. HTTP contract lives with the source:
// https://github.com/brian-nullzone/picket/blob/main/openapi.yaml

async function loadMe() {
  const res = await fetch("/api/me");
  const data = await res.json();
  const n = document.getElementById("credit-count");
  const a = document.getElementById("account-name");
  const p = document.getElementById("plan-name");
  if (n) n.textContent = data.credits;
  if (a) a.textContent = data.account;
  if (p) p.textContent = data.plan;
}

async function loadInvoices() {
  const res = await fetch("/api/invoices");
  const data = await res.json();
  const body = document.getElementById("invoice-body");
  if (!body) return;
  body.innerHTML = (data.invoices || [])
    .map(
      (row) =>
        `<tr><td>${row.id}</td><td>${row.to}</td><td>${row.amount}</td><td>${row.status}</td><td>${row.when}</td></tr>`
    )
    .join("");
}

loadMe();
loadInvoices();
