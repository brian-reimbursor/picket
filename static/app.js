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
  document.querySelectorAll("[data-admin]").forEach((el) => {
    el.style.display = user && user.role === "admin" ? "" : "none";
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
  const note = document.getElementById("pending-note");
  const pending = user.pending_loads || [];
  if (note && pending.length) {
    note.style.display = "";
    note.innerHTML =
      "A " +
      pending[0].amount +
      ' top-up is still confirming. <a href="/account">Retry it from the wallet</a> if the balance did not move.';
  }
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
        <p><button type="button" data-sku="${item.sku}">Add to cart</button></p>
        <p class="err" data-err="${item.sku}"></p>
      </article>`
    )
    .join("");
  root.querySelectorAll("button[data-sku]").forEach((btn) => {
    btn.addEventListener("click", () => addToCart(btn.getAttribute("data-sku")));
  });
  renderCart(user.cart || []);
  const checkout = document.getElementById("cart-checkout");
  if (checkout) checkout.onclick = checkoutCart;
}

async function addToCart(sku) {
  const err = document.querySelector('[data-err="' + sku + '"]');
  const { ok, data } = await api("/api/cart", {
    method: "POST",
    body: JSON.stringify({ sku }),
  });
  if (!ok) {
    if (err) err.textContent = data.error || "could not add";
    return;
  }
  renderCart(data.cart || []);
}

function renderCart(cart) {
  const body = document.getElementById("cart-body");
  const totalEl = document.getElementById("cart-total");
  if (!body) return;
  body.innerHTML = (cart || [])
    .map(
      (row) =>
        `<tr><td>${row.name}</td><td>${row.price}</td><td><button type="button" data-rm="${row.sku}">Remove</button></td></tr>`
    )
    .join("") || `<tr><td colspan="3">Cart is empty.</td></tr>`;
  body.querySelectorAll("[data-rm]").forEach((btn) => {
    btn.addEventListener("click", () => removeFromCart(btn.getAttribute("data-rm")));
  });
  const cents = (cart || []).reduce((n, row) => n + (row.price_cents || 0), 0);
  if (totalEl) totalEl.textContent = money(cents);
}

async function removeFromCart(sku) {
  const { data } = await api("/api/cart/remove", {
    method: "POST",
    body: JSON.stringify({ sku }),
  });
  renderCart(data.cart || []);
}

async function checkoutCart() {
  const err = document.getElementById("cart-err");
  const { ok, data } = await api("/api/cart/checkout", {
    method: "POST",
    body: "{}",
  });
  if (!ok) {
    if (err) {
      err.textContent =
        data.error === "insufficient funds"
          ? "Wallet has " + data.balance + "; cart is " + data.needed + "."
          : data.error || "checkout failed";
    }
    return;
  }
  location.href = "/account";
}

async function applyPending(id) {
  const err = document.getElementById("pending-err");
  const { ok, data } = await api("/api/billing/pending/apply", {
    method: "POST",
    body: JSON.stringify({ id: id }),
  });
  if (!ok) {
    if (err) err.textContent = data.error || "could not apply";
    return;
  }
  loadAccount();
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
  const pendingCard = document.getElementById("pending-card");
  const loads = user.pending_loads || [];
  const pendingAmt = document.getElementById("pending-amount");
  const pendingLabel = document.getElementById("pending-label");
  const pendingBtn = document.getElementById("pending-apply");
  if (pendingCard) {
    pendingCard.style.display = loads.length ? "" : "none";
    if (loads.length) {
      if (pendingAmt) pendingAmt.textContent = loads[0].amount;
      if (pendingLabel) pendingLabel.textContent = loads[0].label;
      if (pendingBtn) {
        pendingBtn.onclick = function () {
          applyPending(loads[0].id);
        };
      }
    }
  }
  const cartBody = document.getElementById("cart-body");
  if (cartBody) {
    const cart = user.cart || [];
    cartBody.innerHTML = cart.length
      ? cart.map((row) => `<tr><td>${row.name}</td><td>${row.price}</td></tr>`).join("")
      : `<tr><td colspan="2">Cart is empty.</td></tr>`;
  }
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
  const cat = document.getElementById("catalog-body");
  const orders = document.getElementById("order-body");
  if (!ok) {
    if (body) body.innerHTML = `<tr><td colspan="5">${data.error || "forbidden"}</td></tr>`;
    return;
  }
  const usersRoot = document.getElementById("admin-users") || body;
  if (usersRoot && usersRoot.id === "admin-users") {
    usersRoot.innerHTML = data.users
      .map((u) => {
        const cart = (u.cart || [])
          .map((row) => row.name + " (" + row.price + ")")
          .join(", ") || "empty";
        return `<article class="card" style="margin-bottom:0.8rem;">
          <p><strong>${u.email}</strong> · ${u.name} · ${u.role}</p>
          <p>Balance ${u.balance}</p>
          <p>Cart: ${cart}</p>
          <p>
            Set USD
            <input data-set="${u.email}" type="number" min="0" step="0.01" value="${(u.balance_cents / 100).toFixed(2)}" style="width:6rem">
            <button type="button" data-set-go="${u.email}">Save</button>
            <button type="button" data-reset="${u.email}">Reset</button>
          </p>
        </article>`;
      })
      .join("");
    usersRoot.querySelectorAll("[data-set-go]").forEach((btn) => {
      btn.addEventListener("click", () => adminSet(btn.getAttribute("data-set-go")));
    });
    usersRoot.querySelectorAll("[data-reset]").forEach((btn) => {
      btn.addEventListener("click", () => adminReset(btn.getAttribute("data-reset")));
    });
  }
  if (cat) {
    cat.innerHTML = (data.catalog || [])
      .map(
        (i) =>
          `<tr>
            <td>${i.sku}</td>
            <td>${i.name}</td>
            <td>${i.price}</td>
            <td>
              <input data-price="${i.sku}" type="number" min="0" step="1" value="${(i.price_cents / 100).toFixed(0)}" style="width:5.5rem">
              <button type="button" data-price-go="${i.sku}">Set</button>
            </td>
          </tr>`
      )
      .join("");
    cat.querySelectorAll("[data-price-go]").forEach((btn) => {
      btn.addEventListener("click", () => adminPrice(btn.getAttribute("data-price-go")));
    });
  }
  if (orders) {
    const rows = data.orders || [];
    orders.innerHTML = rows.length
      ? rows
          .map(
            (row) =>
              `<tr><td>${row.email}</td><td>${row.id}</td><td>${row.name}</td><td>${row.amount}</td></tr>`
          )
          .join("")
      : `<tr><td colspan="4">No orders yet.</td></tr>`;
  }
}

async function adminSet(email) {
  const input = document.querySelector('[data-set="' + email + '"]');
  const amount = input ? Number(input.value) : 0;
  const { ok, data } = await api("/api/admin/users/balance", {
    method: "POST",
    body: JSON.stringify({ email, balance_usd: amount }),
  });
  const err = document.getElementById("admin-err");
  if (!ok) {
    if (err) err.textContent = data.error || "set failed";
    return;
  }
  loadAdmin();
}

async function adminReset(email) {
  const { ok, data } = await api("/api/admin/users/reset", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
  const err = document.getElementById("admin-err");
  if (!ok) {
    if (err) err.textContent = data.error || "reset failed";
    return;
  }
  loadAdmin();
}

async function adminCreate(ev) {
  ev.preventDefault();
  const fd = new FormData(ev.target);
  const { ok, data } = await api("/api/admin/users/create", {
    method: "POST",
    body: JSON.stringify({
      name: fd.get("name"),
      email: fd.get("email"),
      password: fd.get("password"),
      balance_usd: Number(fd.get("balance_usd") || 4.1),
    }),
  });
  const err = document.getElementById("admin-err");
  if (!ok) {
    if (err) err.textContent = data.error || "create failed";
    return;
  }
  ev.target.reset();
  loadAdmin();
}

async function adminPrice(sku) {
  const input = document.querySelector('[data-price="' + sku + '"]');
  const usd = input ? Number(input.value) : 0;
  const nameCell = input && input.closest("tr") ? input.closest("tr").children[1].textContent : sku;
  const { ok, data } = await api("/api/admin/catalog", {
    method: "POST",
    body: JSON.stringify({ sku, name: nameCell, price_cents: Math.round(usd * 100) }),
  });
  const err = document.getElementById("admin-err");
  if (!ok) {
    if (err) err.textContent = data.error || "update failed";
    return;
  }
  loadAdmin();
}

window.picket = {
  boot,
  onRegister,
  onLogin,
  onLogout,
  loadShop,
  loadAccount,
  loadAdmin,
  applyPending,
  adminCreate,
  adminReset,
  adminSet,
};
