/* Listagem dinâmica de extensões (RF11/RF12/RF14).
   Busca a lista consolidada da API (SIGA-IC + externas aprovadas) e renderiza
   os cards com busca e filtros client-side. */
(function () {
  "use strict";

  var container = document.getElementById("lista-extensoes");
  if (!container) return;

  var apiBase = (container.dataset.api || "").replace(/\/$/, "");
  var busca = document.getElementById("extensoes-busca");
  var filtroVagas = document.getElementById("filtro-vagas");
  var filtroBolsa = document.getElementById("filtro-bolsa");
  var dados = [];

  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  }

  function temVagas(e) {
    return e.vagas != null && Number(e.vagas) > 0;
  }

  function cardHTML(e) {
    var meta = "";
    meta += "<dt>Coordenador</dt><dd>" + esc(e.coordenador) + "</dd>";
    if (e.modalidade) meta += "<dt>Modalidade</dt><dd>" + esc(e.modalidade) + "</dd>";
    meta += "<dt>Vagas</dt><dd>" +
      (temVagas(e) ? esc(e.vagas) : '<span class="sem-vagas">Sem vagas no momento</span>') + "</dd>";
    if (e.bolsa != null) meta += "<dt>Bolsa</dt><dd>" + (e.bolsa ? "Sim" : "Não") + "</dd>";
    if (e.processo_seletivo) meta += "<dt>Processo seletivo</dt><dd>" + esc(e.processo_seletivo) + "</dd>";

    var perfil = e.perfil
      ? '<p class="extensao-perfil"><strong>Perfil desejado:</strong> ' + esc(e.perfil) + "</p>" : "";

    var rodape = "";
    if (e.contato) rodape += '<span>Contato: <a href="mailto:' + esc(e.contato) + '">' + esc(e.contato) + "</a></span>";
    if (e.link_inscricao) rodape += '<a href="' + esc(e.link_inscricao) +
      '" target="_blank" rel="noopener">Inscrever-se →</a>';

    var area = e.area ? '<span class="extensao-area">' + esc(e.area) + "</span>" : "";
    var tagOrigem = e.origem === "externa"
      ? '<span class="extensao-area" title="Extensão externa aprovada">externa</span>' : "";

    return '<li><article class="card-extensao">' +
      '<header class="card-extensao-header"><h3>' + esc(e.titulo) + "</h3>" + area + tagOrigem + "</header>" +
      (e.descricao ? '<p class="extensao-descricao">' + esc(e.descricao) + "</p>" : "") +
      '<dl class="extensao-metadados">' + meta + "</dl>" +
      perfil +
      '<footer class="card-extensao-footer">' + rodape + "</footer>" +
      "</article></li>";
  }

  function aplicarFiltros() {
    var termo = (busca && busca.value || "").trim().toLowerCase();
    var soVagas = filtroVagas && filtroVagas.checked;
    var soBolsa = filtroBolsa && filtroBolsa.checked;

    var lista = dados.filter(function (e) {
      if (soVagas && !temVagas(e)) return false;
      if (soBolsa && !e.bolsa) return false;
      if (termo) {
        var blob = [e.titulo, e.coordenador, e.area, e.descricao, e.perfil, e.modalidade]
          .join(" ").toLowerCase();
        if (blob.indexOf(termo) === -1) return false;
      }
      return true;
    });

    if (!lista.length) {
      container.innerHTML = '<p class="extensoes-status">Nenhuma extensão encontrada.</p>';
      return;
    }
    container.innerHTML = '<ul class="lista-extensoes">' + lista.map(cardHTML).join("") + "</ul>";
  }

  function carregar() {
    fetch(apiBase + "/api/extensoes")
      .then(function (r) {
        if (!r.ok) throw new Error("HTTP " + r.status);
        return r.json();
      })
      .then(function (json) {
        dados = Array.isArray(json) ? json : [];
        aplicarFiltros();
      })
      .catch(function (err) {
        container.innerHTML = '<p class="extensoes-status">Não foi possível carregar as extensões agora. ' +
          "Tente novamente mais tarde.</p>";
        if (window.console) console.error("Erro ao carregar extensões:", err);
      });
  }

  [busca, filtroVagas, filtroBolsa].forEach(function (el) {
    if (el) el.addEventListener("input", aplicarFiltros);
  });

  carregar();
})();
