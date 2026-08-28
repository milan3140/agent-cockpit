/* QA:點開一張單時,其他已展開的區塊會不會跟著重播動畫(=整片閃動)。
   判準:點第三張後,第一張的 .detail>.dwrap 不應有 running animation;
   且該次點開的那張應該要有(證明動畫本身沒被關掉)。用 COCKPIT_EVAL 執行。*/
(async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const rowKeys = () => [...document.querySelectorAll(".q[data-k]")].map(q => q.dataset.k)
    .filter(k => k.startsWith("fv:"));
  const clickRow = (k) => {
    const q = document.querySelector('.q[data-k="' + CSS.escape(k) + '"]');
    if (q) q.click();
  };
  const anims = (k) => {   // 該單的 detail 內有幾個正在跑的動畫
    const q = document.querySelector('.q[data-k="' + CSS.escape(k) + '"]');
    const d = q && q.nextElementSibling;
    if (!d || !d.classList.contains("detail")) return -1;
    const w = d.querySelector(".dwrap");
    return w ? w.getAnimations().filter(a => a.playState === "running").length : -1;
  };
  const ks = rowKeys();
  if (ks.length < 3) return "need>=3 rows, got " + ks.length;
  const [a, b, c] = ks;
  clickRow(a); await sleep(500);
  clickRow(b); await sleep(500);
  clickRow(c); await sleep(60);              // 第三張剛點開
  const first = anims(a), third = anims(c);
  await sleep(500);
  return "已展開的第一張 running=" + first + "(要 0) | 剛點的第三張 running=" + third + "(要 >=1)";
})()
