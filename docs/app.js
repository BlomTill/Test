(function () {
  const c = window.SITE_CONFIG;
  if (!c) {
    document.body.innerHTML =
      "<p>Missing <code>config.js</code>. Restore it next to <code>index.html</code>.</p>";
    return;
  }

  document.getElementById("site-name").textContent = c.name;
  document.getElementById("tagline").textContent = c.tagline;
  document.getElementById("bio").textContent = c.bio || "";

  const list = document.getElementById("link-list");
  list.innerHTML = "";
  (c.links || []).forEach(function (item) {
    if (!item.url || item.url.includes("example.com")) return;
    const li = document.createElement("li");
    const a = document.createElement("a");
    a.href = item.url;
    a.rel = "noopener noreferrer";
    a.target = "_blank";
    a.textContent = item.label;
    li.appendChild(a);
    if (item.hint) {
      const span = document.createElement("span");
      span.className = "hint";
      span.textContent = item.hint;
      li.appendChild(span);
    }
    list.appendChild(li);
  });

  if (!list.children.length) {
    const li = document.createElement("li");
    li.className = "placeholder";
    li.textContent =
      "Add real URLs in config.js (replace example.com links), then refresh.";
    list.appendChild(li);
  }

  const foot = document.getElementById("footer-links");
  foot.innerHTML = "";
  (c.footerLinks || []).forEach(function (item) {
    if (!item.url) return;
    const a = document.createElement("a");
    a.href = item.url;
    a.rel = "noopener noreferrer";
    a.textContent = item.label;
    foot.appendChild(a);
  });

  const disc = document.getElementById("affiliate-note");
  if (c.hasAffiliateDisclosure) {
    disc.hidden = false;
  }

  fetch("trending.json")
    .then(function (r) {
      if (!r.ok) throw new Error(r.status);
      return r.json();
    })
    .then(function (data) {
      var tl = document.getElementById("trending-list");
      var tu = document.getElementById("trending-updated");
      if (!data || !data.items || !data.items.length) {
        tl.innerHTML =
          '<li class="placeholder">No trending items yet — run build_news.py.</li>';
        return;
      }
      if (tu && data.updated) {
        tu.textContent = "Updated " + data.updated;
      }
      tl.innerHTML = "";
      data.items.forEach(function (item) {
        var li = document.createElement("li");
        var a = document.createElement("a");
        a.href = item.url;
        a.rel = item.affiliate
          ? "noopener noreferrer sponsored"
          : "noopener noreferrer";
        a.target = "_blank";
        a.textContent = item.title;
        li.appendChild(a);
        if (item.source) {
          var span = document.createElement("span");
          span.className = "hint";
          span.textContent = item.source;
          li.appendChild(span);
        }
        tl.appendChild(li);
      });
      if (data.items.some(function (i) { return i.affiliate; })) {
        disc.hidden = false;
      }
    })
    .catch(function () {
      var tl = document.getElementById("trending-list");
      tl.innerHTML =
        '<li class="placeholder">Could not load trending picks.</li>';
    });
})();
