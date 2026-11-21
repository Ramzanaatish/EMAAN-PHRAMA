Pharma Purchase Assistant v1.3.0 — HTML + Server setup
=====================================================

Is folder mein ye cheezein hain:
  1. Pharma-Purchase-Assistant.html — dashboard (double-click se khulti hai)
  2. start-server.bat — ek click mein server + HTML dono chala deta hai
  3. server.spec — PharmaServer.exe banane ki recipe (developer ke liye)

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
2. Actions tab -> sab se upar wali CI run (v1.3.0) kholein.
3. Neeche Artifacts mein "PharmaServer" download karein.
4. ZIP khol kar PharmaServer.exe is folder mein rakhein.
   (Desktop Setup bhi usi run ke "PharmaPurchaseAssistant-Setup"
   artifact mein hai — Setup-1.3.0.exe.)

ZAROORI SHART
-------------
- Server aur HTML ek hi PC par chalte hain (woh PC jis par SmilePOS hai).
- Akele HTML file SQL Server se nahi jud sakti — server chalta rehna
  lazmi hai, warna page demo data dikhata hai.
- POS_DB se data sirf parha jata hai (read-only) — kuch likha nahi jata.
- Server: http://127.0.0.1:5000 — port 5000.
