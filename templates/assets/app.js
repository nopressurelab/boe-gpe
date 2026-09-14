// Filtrado en cliente sobre la lista ya renderizada en el HTML.
(function () {
  "use strict";
  var list = document.getElementById("items");
  if (!list) return;
  var q = document.getElementById("q");
  var fSource = document.getElementById("f-source");
  var fTopic = document.getElementById("f-topic");
  var counter = document.getElementById("count");
  var empty = document.getElementById("empty");
  var items = Array.prototype.slice.call(list.querySelectorAll(".item"));
  var total = items.length;
  var haystacks = items.map(function (el) { return normalize(el.textContent); });

  function normalize(value) {
    return (value || "").toLowerCase().normalize("NFD").replace(/[\u0300-\u036f]/g, "");
  }

  function apply() {
    var needle = normalize(q && q.value);
    var source = (fSource && fSource.value) || "";
    var topic = (fTopic && fTopic.value) || "";
    var shown = 0;
    for (var i = 0; i < items.length; i++) {
      var el = items[i];
      var ok = true;
      if (source && el.dataset.source !== source) ok = false;
      if (ok && topic && (" " + el.dataset.topics + " ").indexOf(" " + topic + " ") === -1) ok = false;
      if (ok && needle && haystacks[i].indexOf(needle) === -1) ok = false;
      el.hidden = !ok;
      if (ok) shown++;
    }
    if (counter) counter.textContent = shown + " de " + total;
    if (empty) empty.hidden = shown !== 0;
    syncUrl(source, topic, q && q.value);
  }

  function syncUrl(source, topic, text) {
    if (!window.history || !window.history.replaceState) return;
    var params = new URLSearchParams();
    if (source) params.set("fuente", source);
    if (topic) params.set("tema", topic);
    if (text) params.set("q", text);
    var query = params.toString();
    window.history.replaceState(null, "", query ? "?" + query : location.pathname);
  }

  function restore() {
    var params = new URLSearchParams(location.search);
    if (fSource && params.get("fuente")) fSource.value = params.get("fuente");
    if (fTopic && params.get("tema")) fTopic.value = params.get("tema");
    if (q && params.get("q")) q.value = params.get("q");
  }

  [q, fSource, fTopic].forEach(function (el) {
    if (!el) return;
    el.addEventListener("input", apply);
    el.addEventListener("change", apply);
  });
  restore();
  apply();
})();
