import { tr } from "./i18n";

export async function saveFile(blob: Blob, filename: string): Promise<string> {
  const bridge = (window as any).pywebview?.api;
  if (bridge?.save_file) {
    const encoded = await new Promise<string>((resolve, reject) => {
      const reader = new FileReader();
      reader.onerror = () => reject(new Error(tr("Не удалось прочитать экспорт")));
      reader.onload = () => resolve(String(reader.result).split(",", 2)[1]);
      reader.readAsDataURL(blob);
    });
    const result = await bridge.save_file(filename, encoded);
    if (result.status === "cancelled") return tr("Сохранение отменено");
    if (result.status !== "saved") throw new Error(result.message || tr("Не удалось сохранить файл"));
    return tr("Файл сохранён:") + " " + result.path;
  }
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 30000);
  return tr("Файл передан браузеру:") + " " + filename + ". " + tr("Откройте загрузки браузера (Ctrl+J), чтобы увидеть папку сохранения.");
}
