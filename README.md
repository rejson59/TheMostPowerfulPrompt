# OMNICOGNITION 5.0 „SINGULARITY"

**Najdłuższy i najpotężniejszy system prompt w tym repozytorium** — uniwersalny
metapoznawczy system operacyjny dla modeli językowych. Dwie pełne wersje
(angielska i polska), gotowa strona do przeglądania i kopiowania, testy.

---

## ⚠️ Uczciwa deklaracja

**Żaden prompt nie podnosi inteligencji modelu 1000× i nie tworzy AGI.** Pojemność
modelu jest ustalona w treningu — prompt nie dodaje wiedzy ani nie przyspiesza
obliczeń.

Ten dokument robi coś innego i mierzalnego: eliminuje **niepotrzebne** błędy,
przez które nawet dobre modele wypadają głupio — halucynacje, pochlebstwo,
pompowanie objętości, przedwczesną zbieżność, łatanie objawów, dryf poza pytanie.
Wymusza jawne rozumowanie, samoweryfikację i kalibrację pewności. Największy zysk
jest na małych modelach, bo tam startowy pułap jest najniższy.

---

## Pliki

| Plik | Co to jest |
|---|---|
| `prompt/EN.md` | **Główny prompt.** 9 580 słów, ~61,4 tys. znaków, ~15,3 tys. tokenów, 15 części. Używaj tej wersji — modele najlepiej wykonują instrukcje po angielsku. |
| `prompt/PL.md` | Pełny polski odpowiednik, 6 013 słów, 15 części. Dla rozmów prowadzonych po polsku. |
| `prompt/variants/` | Gotowe do wklejenia warianty `LITE` i jednozdaniowy, wyciągane automatycznie z dodatków. |
| `index.html` | Samodzielna strona (zero zależności, działa offline) z podglądem, wyszukiwarką, spisem treści i kopiowaniem per sekcja. |
| `build.py` | Buduje `index.html` z `prompt/*.md`. Własny renderer markdowna, bez bibliotek. |
| `template.html` | Szablon strony (CSS + JS). |
| `test/page.test.mjs` | 57 asercji wykonywanych na prawdziwej stronie w jsdom. |
| `deploy/pages.yml.example` | Gotowy workflow GitHub Pages. **Nieaktywny tam, gdzie leży** — skopiuj go do `.github/workflows/pages.yml` we własnym klonie (szczegóły w nagłówku pliku). |

---

## Szybki start

**Chcesz tylko prompt?** Otwórz `prompt/EN.md`, skopiuj całość, wklej do slotu
systemowego. Dla małych modeli (≤3B) użyj wyłącznie wariantu `LITE` z Dodatku B —
pełny dokument zje im budżet kontekstu potrzebny na samo zadanie.

**Chcesz stronę?**

```bash
python3 -m http.server 8000     # albo po prostu otwórz index.html
```

**Publikacja.** Workflow leży w `deploy/pages.yml.example` i nie jest aktywny —
automatyzacja pushująca to repo nie ma uprawnienia `workflows`, więc nie może
utworzyć `.github/workflows/`. Skopiuj plik samodzielnie:

```bash
mkdir -p .github/workflows
cp deploy/pages.yml.example .github/workflows/pages.yml
git add .github/workflows/pages.yml && git commit -m 'Add Pages workflow' && git push
```

Potem w repo: Settings → Pages → Source: **GitHub Actions**. Strona pojawi się pod
`https://rejson59.github.io/TheMostPowerfulPrompt/`.

**Chcesz edytować prompt i przebudować stronę?**

```bash
vim prompt/EN.md
python3 build.py                # -> index.html
```

**Chcesz uruchomić testy?**

```bash
npm install --no-save jsdom
node test/page.test.mjs
```

---

## Warianty według rozmiaru modelu

| Klasa modelu | Wariant |
|---|---|
| Frontier (duży, silne rozumowanie) | Cały dokument. Wykorzysta wszystko. |
| Średni (7B–30B) | Części 0, I, II, IV, VI, X. Dodatki pomiń. |
| Mały (≤3B) | Tylko `LITE` (Dodatek B). Więcej = gorzej. |

Temperatura: 0.2–0.5 dla rozumowania, kodu i faktów; 0.8–1.1 dla kreacji.
Jeśli model nie ma narzędzi, usuń sekcje 7.1–7.2.

---

## Co jest w środku

**Część 0** — Dyrektywa główna i trzy prawa nienegocjowalne
**I** — Architektura poznawcza: siedmiofazowa pętla rozumowania, budżet głębokości,
rejestr niepewności, zejście do zasad pierwszych, higiena rozumowania
**II** — Protokoły epistemiczne: łańcuch weryfikacji (CoVe), zapora antyhalucynacyjna,
kalibracja, trzech recenzentów, wykrywanie fałszywych przesłanek
**III** — Matematyka i ilości: licz-don't-recall, Pólya rozszerzona, Fermi, statystyka
**IV** — Kod i inżynieria: kontrakt inżynierski, reguły pisania, samoweryfikacja,
protokół debugowania, bezpieczeństwo, projektowanie
**V** — Planowanie i decyzje: dekompozycja celu, pre-mortem, ramy decyzyjne
**VI** — Komunikacja: adaptacyjna głębokość, struktura, wzorce zakazane, ton
**VII** — Narzędzia i zachowanie agentowe: pętla agentowa, dyscyplina kontekstu
**VIII** — Bezpieczeństwo i integralność: kalibracja odmów, uczciwość pod presją
**IX** — Metapoznanie: samomonitorowanie, odzyskiwanie po błędzie, pętla doskonalenia
**X** — Praca twórcza: pułapka generyczności, protokół rozbieżności, głos i rejestr,
twarde ograniczenia formalne, przebieg redakcyjny, mechanika humoru
**XI** — Wyjaśnianie i tłumaczenie: diagnoza realnej luki, drabina wyjaśniania,
analogie z granicami, weryfikacja zrozumienia, zachowanie rejestru
**XII** — Długie formy: struktura przed prozą, kontrakt akapitu, czteropoziomowa
redakcja, dyscyplina objętości, anty-błoto
**XIII** — Odporność adwersarzowa: granica zaufania, taksonomia ośmiu wstrzyknięć,
samouzgadnianie, najsilniejsza wersja obu stron, red team na własnym wyjściu
**XIV** — Katalog 28 trybów awarii z poprawkami + brama końcowa
**XV** — Aktywacja
**Dodatki** — noty wdrożeniowe, wariant `LITE` (14 reguł), wariant jednozdaniowy

---

## Licencja

CC0 / domena publiczna. Używaj, zmieniaj, sprzedawaj.
