import i18n from "i18next";
import { initReactI18next } from "react-i18next";
import enCommon from "./locales/en/common.json";
import ruCommon from "./locales/ru/common.json";

const storedLanguage = localStorage.getItem("oma_lang");
const initialLanguage = storedLanguage === "ru" || storedLanguage === "en" ? storedLanguage : "en";

void i18n.use(initReactI18next).init({
  resources: {
    en: { common: enCommon },
    ru: { common: ruCommon },
  },
  lng: initialLanguage,
  fallbackLng: "en",
  defaultNS: "common",
  interpolation: { escapeValue: false },
});

void i18n.on("languageChanged", (nextLanguage) => {
  localStorage.setItem("oma_lang", nextLanguage.startsWith("ru") ? "ru" : "en");
});

export default i18n;
