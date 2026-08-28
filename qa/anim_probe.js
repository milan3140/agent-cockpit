(async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const gr = (el) => el ? getComputedStyle(el).gridTemplateRows : "none";
  const bodyOf = (fk) => document.querySelector('.fvbody[data-fb="' + CSS.escape(fk) + '"]');
  const out = [];
  // 找一個目前「收合中」的功能塊來測展開(重渲染後要用 fk 重新查詢,不能用舊參照)
  const closed = [...document.querySelectorAll(".fvh3")].find(h => !h.parentElement.querySelector(".fvbody"));
  if (!closed) return "no-collapsed-block";
  const fk = closed.dataset.tg;
  closed.click();
  await sleep(120);
  const a = gr(bodyOf(fk));      // 展開起點(應接近 0px)
  await sleep(120);
  const b = gr(bodyOf(fk));      // 中途
  await sleep(300);
  const c = gr(bodyOf(fk));      // 終點(完整高度)
  out.push("EXPAND " + a + " → " + b + " → " + c);
  return out.join(" | ");
})()
