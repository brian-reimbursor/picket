// Workspace bootstrap. HTTP contract lives with the source:
// https://github.com/brian-reimbursor/picket/blob/main/docs/openapi.yaml

async function api(path, opts) {
  const res = await fetch(path, {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json", ...(opts && opts.headers) },
    ...opts,
  });
  const data = await res.json().catch(() => ({}));
  return { ok: res.ok, status: res.status, data };
}

function money(cents) {
  return "$" + (cents / 100).toFixed(2);
}

async function currentUser() {
  const { ok, data } = await api("/api/me");
  return ok ? data : null;
}

function paintNav(user) {
  const who = document.getElementById("who");
  const authed = document.querySelectorAll("[data-auth]");
  const guest = document.querySelectorAll("[data-guest]");
  authed.forEach((el) => {
    el.style.display = user ? "" : "none";
  });
  guest.forEach((el) => {
    el.style.display = user ? "none" : "";
  });
  if (who && user) who.textContent = user.email;
}

async function boot() {
  const user = await currentUser();
  paintNav(user);
  return user;
}

async function onRegister(ev) {
  ev.preventDefault();
  const fd = new FormData(ev.target);
  const { ok, data } = await api("/api/auth/register", {
    method: "POST",
    body: JSON.stringify({
      name: fd.get("name"),
      email: fd.get("email"),
      password: fd.get("password"),
    }),
  });
  const err = document.getElementById("auth-err");
  if (!ok) {
    if (err) err.textContent = data.error || "could not create account";
    return;
  }
  location.href = "/shop";
}

async function onLogin(ev) {
  ev.preventDefault();
  const fd = new FormData(ev.target);
  const { ok, data } = await api("/api/auth/login", {
    method: "POST",
    body: JSON.stringify({
      email: fd.get("email"),
      password: fd.get("password"),
    }),
  });
  const err = document.getElementById("auth-err");
  if (!ok) {
    if (err) err.textContent = data.error || "sign-in failed";
    return;
  }
  location.href = "/shop";
}

async function onLogout() {
  await api("/api/auth/logout", { method: "POST", body: "{}" });
  location.href = "/";
}

async function loadShop() {
  const user = await boot();
  if (!user) {
    location.href = "/";
    return;
  }
  const bal = document.getElementById("balance");
  if (bal) bal.textContent = user.balance;
  const { data } = await api("/api/catalog");
  const root = document.getElementById("products");
  if (!root) return;
  root.innerHTML = (data.items || [])
    .map(
      (item) => `
      <article class="card">
        <h2 style="margin:0;font-size:1.05rem;">${item.name}</h2>
        <p class="price">${item.price}</p>
        <p>${item.blurb}</p>
        <p><button type="button" data-sku="${item.sku}">Buy</button></p>
        <p class="err" data-err="${item.sku}"></p>
      </article>`
    )
    .join("");
  root.querySelectorAll("button[data-sku]").forEach((btn) => {
    btn.addEventListener("click", () => buy(btn.getAttribute("data-sku")));
  });
}

async function buy(sku) {
  const err = document.querySelector('[data-err="' + sku + '"]');
  const { ok, data } = await api("/api/orders", {
    method: "POST",
    body: JSON.stringify({ sku }),
  });
  if (!ok) {
    if (err) {
      err.textContent =
        data.error === "insufficient funds"
          ? "Wallet has " + data.balance + "; this item is " + data.needed + "."
          : data.error || "could not buy";
    }
    return;
  }
  location.href = "/account";
}

async function loadAccount() {
  const user = await boot();
  if (!user) {
    location.href = "/";
    return;
  }
  const bal = document.getElementById("balance");
  const mail = document.getElementById("email");
  const name = document.getElementById("name");
  if (bal) bal.textContent = user.balance;
  if (mail) mail.textContent = user.email;
  if (name) name.textContent = user.name;
  const body = document.getElementById("order-body");
  if (!body) return;
  const rows = user.orders || [];
  body.innerHTML = rows.length
    ? rows
        .map(
          (row) =>
            `<tr><td>${row.id}</td><td>${row.name}</td><td>${row.amount}</td><td>${row.when}</td></tr>`
        )
        .join("")
    : `<tr><td colspan="4">No purchases yet.</td></tr>`;
}

async function loadAdmin() {
  const user = await boot();
  if (!user) {
    location.href = "/";
    return;
  }
  const { ok, data } = await api("/api/admin/users");
  const body = document.getElementById("admin-body");
  if (!ok) {
    if (body) body.innerHTML = `<tr><td colspan="4">${data.error || "forbidden"}</td></tr>`;
    return;
  }
  body.innerHTML = data.users
    .map(
      (u) =>
        `<tr><td>${u.email}</td><td>${u.name}</td><td>${u.role}</td><td>${u.balance}</td></tr>`
    )
    .join("");
}

window.picket = {
  boot,
  onRegister,
  onLogin,
  onLogout,
  loadShop,
  loadAccount,
  loadAdmin,
};
