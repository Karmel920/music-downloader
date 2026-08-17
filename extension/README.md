# YT MP3 Downloader (wtyczka Chrome + lokalny serwer)

Wtyczka do Chrome, która dodaje przyciski **"Pobierz utwór"** i **"Pobierz playlistę"** na stronach YouTube.
Samo pobieranie i konwersję do MP3 320 kbps wykonuje serwer w Pythonie (`yt-dlp` + `ffmpeg`, ta sama logika
co w głównym skrypcie repo). Serwer może działać lokalnie **lub na zdalnej maszynie** (np. serwerze domowym).

## Jak trafiają pliki na Twój komputer

Serwer pobiera i konwertuje pliki do folderu **tymczasowego** u siebie, a następnie wtyczka ściąga gotowy
plik do folderu **Pobrane** przeglądarki na komputerze, z którego korzystasz. Po wysłaniu serwer kasuje pliki
tymczasowe. Dzięki temu serwer może stać gdziekolwiek, a muzyka i tak ląduje lokalnie u Ciebie.

- Pojedynczy utwór -> jeden plik MP3.
- Playlista -> jeden plik **ZIP** z całą playlistą (z podfolderami per-artysta w środku).

```
extension/
  server/            # lokalny backend HTTP (Python + yt-dlp)
    server.py
    requirements.txt
    config.example.json
  chrome/            # rozszerzenie Chrome (Manifest V3)
    manifest.json
    content.js / content.css
    popup.html / popup.js / popup.css
```

## 1. Wymagania

- Python 3.10+
- `ffmpeg` w `PATH`
- JavaScript runtime: `deno` (preferowany) lub `node`
- Chrome / Edge (dowolna przeglądarka na silniku Chromium)

Instalacja narzędzi systemowych (Windows):

```powershell
winget install Gyan.FFmpeg
winget install DenoLand.Deno
```

## 2. Uruchomienie serwera

```powershell
python -m pip install -r extension/server/requirements.txt
python extension/server/server.py
```

Serwer nasłuchuje na `0.0.0.0:8765` (dostępny też z innych urządzeń w sieci). Zostaw go uruchomionego w tle.
Na maszynie lokalnej używaj `http://127.0.0.1:8765`, a przy serwerze domowym wpisz w popupie jego adres
w sieci LAN, np. `http://192.168.1.10:8765`.

## 3. Instalacja wtyczki w Chrome

1. Otwórz `chrome://extensions`.
2. Włącz **Tryb programisty** (Developer mode).
3. Kliknij **Wczytaj rozpakowane** (Load unpacked) i wskaż folder `extension/chrome`.

## 4. Konfiguracja

Kliknij ikonę wtyczki, aby otworzyć popup:

- **Adres serwera** - `http://127.0.0.1:8765` (lokalnie) lub adres serwera w LAN.
- **Podfolder w Pobranych** - opcjonalny podfolder w folderze Pobrane przeglądarki, np. `YouTube`
  (puste = prosto do Pobranych). Ścieżki bezwzględne i dyski nie są obsługiwane - to musi być względna nazwa.
- **Format** - domyślnie `mp3`.
- **Jakość** - domyślnie `320` kbps.

Przyciskiem **Sprawdź serwer** zweryfikujesz połączenie.

## 5. Użycie

- Na stronie filmu (`/watch`) pojawia się przycisk **"Pobierz utwór"**.
- Jeśli film jest częścią playlisty (parametr `list=`), obok pojawia się **"Pobierz playlistę"**.
- Na stronie playlisty (`/playlist`) dostępny jest przycisk **"Pobierz playlistę"**.

Postęp (procent / konwersja / liczba pobranych utworów) jest pokazywany bezpośrednio na przycisku.

## Uwagi

- YouTube to aplikacja SPA - wtyczka sama wykrywa zmiany strony i ponownie wstawia przyciski.
- Serwer wykonuje jedno zadanie na żądanie w osobnym wątku; kilka pobrań może działać równolegle.
- Playlisty pobierane są w całości przez `yt-dlp` (opcja `noplaylist=false`) i dostarczane jako ZIP.
- Pliki tymczasowe trzymane są w katalogu tymczasowym systemu (`.../ytmp3dl/<job>`) i kasowane po wysłaniu.
- **Bezpieczeństwo:** serwer nie ma uwierzytelniania i przyjmuje żądania z całej sieci. Wystawiaj go tylko
  w zaufanej sieci LAN, nigdy bezpośrednio do internetu bez dodatkowej ochrony (VPN / reverse proxy z hasłem).
