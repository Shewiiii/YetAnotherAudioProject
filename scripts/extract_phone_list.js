(() => {
  const extracted = allPhones.map(item => ({
    brand: item.dispBrand,
    phone: item.phone,
    fullName: item.fullName,
    fileName: item.fileName,
    dispNames: item.dispNames || [item.dispName]
  }));

  const jsonStr = JSON.stringify(extracted, null, 2);
  const blob = new Blob([jsonStr], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");

  a.href = url;
  a.download = "website_phones.json";
  a.click();
  URL.revokeObjectURL(url);

  console.log(`Downloaded ${extracted.length} IEMs as 'website_phones.json'.`);
})();