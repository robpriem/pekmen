# Pacman - Capture the Flag: _[Teamnaam]_

Deze repo dient als inzending voor het toernooi "Pacman - Capture the Flag".
In `my_team.py` werd(en) de klasse(n) geïmplementeerd waarmee een team van twee agents geïnstantieerd kan worden in het `capture-the-flag` framework.

## 📥 Inzending

### Studiedeel
- **Opleiding:** [Bachelor in de artificiële intelligentie](https://caliweb.vub.be/?page=program&id=00721)
- **Studiedeel:** [AI Programmeerproject](https://caliweb.vub.be/?page=course-offers&id=011970)
- **Academiejaar:** _[academiejaar]_
- **Onderwijsteam:** Lynn Houthuys, Arno Temmerman

### Groepsleden
- Student 1 Naam - e-mail - Github id
- Student 2 Naam - e-mail - Github id


## 📚 Documentatie
Om dit team van agents uit te proberen in een spel "Capture the Flag" moet je in eerste instantie het `capture-the-flag` framework gedownload hebben van Canvas of van volgende [GitHub repo]().
Vervolgens raden we aan om de huidige repo (degene waar je nu de README van leest) te clonen/downloaden en als "team-map" te plaatsen in de `agents/` directory van het framwork.

```
capture-the-flag/
├─ agents/
│  └─ [naam van deze repo]/
│     ├─ my_team.py
│     └─ README.md
⋮
├─ capture.py
⋮
└─ VERSION
```

Vervolgens kan je vanuit de `capture-the-flag` directory jouw agents (bijvoorbeeld als het rode team) laten spelen:
```bash
python capture.py -r agents/[naam-van-deze-repo]/my_team.py
```