// Written with ChatGPT
// Download every active phone (average active channels/curves)
// Should be used in JS Console of 
// https://graph.hangout.audio/iem/5128/ 
// https://earphonesarchive.squig.link/ 
// and https://listener800.github.io/5128iem.html only

(() => {
    const INCLUDE_TARGETS = false;

    const clean = (s) =>
        String(s ?? "unknown")
            .replace(/[<>:"/\\|?*\x00-\x1F]/g, "_")
            .replace(/\s+/g, " ")
            .trim();

    const download = (name, text) => {
        const blob = new Blob([text], { type: "text/plain" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = name;
        a.click();
        setTimeout(() => URL.revokeObjectURL(a.href), 30000);
    };

    const interp = (curve, f) => {
        if (f <= curve[0][0]) return curve[0][1];
        if (f >= curve[curve.length - 1][0]) return curve[curve.length - 1][1];

        let lo = 0;
        let hi = curve.length - 1;

        while (hi - lo > 1) {
            const mid = Math.floor((lo + hi) / 2);
            if (curve[mid][0] < f) lo = mid;
            else hi = mid;
        }

        const [f1, y1] = curve[lo];
        const [f2, y2] = curve[hi];
        return y1 + (y2 - y1) * ((f - f1) / (f2 - f1));
    };

    const isPoint = (value) =>
        Array.isArray(value) && value.length >= 2 &&
        typeof value[0] === "number" && typeof value[1] === "number";

    const getCurves = (p) => {
        // Prioritize activeCurves; fall back to rawChannels or channels if missing
        const src = (Array.isArray(p.activeCurves) && p.activeCurves.length > 0)
            ? p.activeCurves
            : (p.rawChannels || p.channels);

        if (!src) return null;

        // Directly formatted curve: [[freq, dB], ...]
        if (Array.isArray(src) && isPoint(src[0])) return [src];
        if (!Array.isArray(src)) return null;

        // Extract curve data from objects ({ l: [...] }) or raw point arrays
        return src
            .map((item) => (item && Array.isArray(item.l) ? item.l : item))
            .filter((item) => Array.isArray(item) && isPoint(item[0]));
    };

    const averageCurves = (curves) => {
        if (!Array.isArray(curves) || curves.length === 0) return null;

        // Already averaged or single channel
        if (curves.length === 1) return curves[0];

        const [base, ...rest] = curves;
        return base.map(([f, y0]) => {
            let sum = y0;
            for (let i = 0; i < rest.length; i++) {
                sum += interp(rest[i], f);
            }
            return [f, sum / curves.length];
        });
    };

    activePhones.forEach((p) => {
        if (!INCLUDE_TARGETS && p.isTarget) return;

        const curves = getCurves(p);
        const avg = averageCurves(curves);
        if (!avg) return;

        const brand = p.dispBrand || p.brand?.name || "";
        const model = p.dispName || p.phone || p.fullName || p.fileName;

        const filename = clean(`${brand} ${model}.txt`);

        const txt =
            avg.map(([f, db]) => `${f} ${db.toFixed(15)}`).join("\n") + "\n";

        download(filename, txt);
    });
})();