document.querySelectorAll("[data-toggle]").forEach(function (button) {
  button.addEventListener("click", function () {
    var detailRow = button.closest("tr").nextElementSibling;
    detailRow.hidden = !detailRow.hidden;
    button.textContent = detailRow.hidden ? "Details" : "Hide";
  });
});

var auto = document.getElementById("auto");

if (auto) {
  var timer = null;

  function setAuto(on) {
    clearInterval(timer);
    if (on) {
      timer = setInterval(function () { location.reload(); }, 30000);
    }
    try { localStorage.setItem("wa_auto_refresh", on ? "1" : "0"); } catch (e) {}
  }

  try { auto.checked = localStorage.getItem("wa_auto_refresh") === "1"; } catch (e) {}
  setAuto(auto.checked);
  auto.addEventListener("change", function () { setAuto(auto.checked); });
}
