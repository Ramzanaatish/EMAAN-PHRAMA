Pharma Purchase Assistant v1.3.3 — HTML + Server setup
=====================================================

Is folder mein ye cheezein hain:
  1. Pharma-Purchase-Assistant.html — dashboard (double-click se khulti hai)
  2. start-server.bat — ek click mein server + HTML dono chala deta hai
  3. server.spec — PharmaServer.exe banane ki recipe (developer ke liye)

v1.3.3 MEIN NAYA
----------------
- Out-of-stock medicines sab se pehle, aur sab se recent sale wali
  sab se upar — All Stock, Reorder Suggestions aur Urgent list mein.
  Har row mein "aakhri sale" tareekh nazar aati hai.
- Out-of-stock medicines ab chhupti nahi (server ka exact filter:
  khareedi hui item chahe fields zero hon, dikhti hai).
- All Stock mein aik waqt mein sirf 50 rows dikhti hain (memory ke
  liye) — neeche "Show more" button har dafa mazeed 50 dikhata hai.
- Sirf wo medicines dikhti hain jin ki stock entry pehle kam-az-kam
  1 dafa hui ho (purchase ya opening stock ka record) — poora catalogue
  nahi. Server ye filter import par lagata hai; HTML mein bhi yehi
  filter hai jo server ke purane version ke saath bhi kaam karta hai.
- Suggestions: sales wali tareekh ka column ab probe kar ke chuna
  jata hai — agar POS se sales data nahi aa raha to page saaf batata
  hai ke ADS 0 hai, aur server window mein Refresh ke baad diagnosis
  (sales rows / items with sales) nazar aati hai.

NOTE: Is ZIP mein PharmaServer.exe NAHI hai — woh GitHub Actions se
download kar ke is folder mein rakhein (tareeqa neeche hai).

CHALANE KA TAREEQA (sab se chhota rasta)
------------------------------------------
1. start-server.bat par double-click karein.
   - Pehle server chalega (chhoti minimized window).
   - Phir HTML file browser mein khul jayegi — live data khud aa jayega.
2. Band karne ke liye browser band karein aur PharmaServer wali window band karein.

CMD se chalana ho to:
  cd <is folder ka path>
  start-server.bat

AGAR "Server nahi chal raha" LIKHA AAYE
------------------------------------------
- start-server.bat dobara chalao.
- PharmaServer.exe is folder mein hai ya nahi, check karo.

PharmaServer.exe KAHAN SE LAYEIN (ek dafa)
--------------------------------------------
1. GitHub kholein: github.com/Ramzanaatish/EMAAN-PHRAMA
2. Actions tab -> sab se upar wali CI run (v1.3.3) kholein.
3. Neeche Artifacts mein "PharmaServer" download karein.
4. ZIP khol kar PharmaServer.exe is folder mein rakhein.
   (Desktop Setup bhi usi run ke "PharmaPurchaseAssistant-Setup"
   artifact mein hai — Setup-1.3.3.exe.)

ZAROORI SHART
-------------
- Server aur HTML ek hi PC par chalte hain (woh PC jis par SmilePOS hai).
- Akele HTML file SQL Server se nahi jud sakti — server chalta rehna
  lazmi hai, warna page demo data dikhata hai.
- POS_DB se data sirf parha jata hai (read-only) — kuch likha nahi jata.
- Server: http://127.0.0.1:5000 — port 5000.
