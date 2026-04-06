import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import enCommon from "./locales/en/common.json";
import ruCommon from "./locales/ru/common.json";
import trCommon from "./locales/tr/common.json";

const storedLanguage = localStorage.getItem("oma_lang");
const initialLanguage = storedLanguage === "ru" || storedLanguage === "en" || storedLanguage === "tr" ? storedLanguage : "ru";

void i18n.use(initReactI18next).init({
  resources: {
    en: { common: enCommon },
    ru: { common: ruCommon },
    tr: { common: trCommon },
  },
  lng: initialLanguage,
  fallbackLng: "en",
  defaultNS: "common",
  interpolation: { escapeValue: false },
});

void i18n.on("languageChanged", (nextLanguage) => {
  const normalized = nextLanguage.startsWith("ru") ? "ru" : nextLanguage.startsWith("tr") ? "tr" : "en";
  localStorage.setItem("oma_lang", normalized);
});

export default i18n;
