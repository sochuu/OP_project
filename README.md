# Прогноз налогов (веб-приложение, РФ)

Инструмент для фрилансера: учёт заработков и прогноз налога до конца календарного года
с учётом сезонности спроса. Курсовой проект по ОП 3-го семестра

## Режимы

- **НПД (самозанятость)**
  - доход от физлиц: 4%, при бонусе — 3%;
  - доход от ИП/юрлиц: 6%, при бонусе — 4%;
  - бонус (вычет) до 10 000 ₽: расход 1% базы ФЛ и 2% базы организаций;
  - лимит дохода 2 400 000 ₽.
- **УСН «доходы»** — ставка по умолчанию 6% (можно изменить).
- **НДФЛ** — ставка по умолчанию 13%.

## Прогноз

По месячным суммам строится линейная регрессия на NumPy (МНК): тренд + sin/cos сезона
pandas и scikit-learn VPS не тянет ):

## Запуск

Код на Python, ОС сервера не важна. Windows-пути нужны только если крутишь у себя в VS Code.
Прод — Ubuntu 22.04 на VPS.

### Ubuntu 22.04 (VPS)

```
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
cd /opt
sudo git clone <repo> tax-forecast   # или скопировать папку Kursach
cd tax-forecast
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
chmod +x run.sh
./run.sh
```

Либо systemd (файл `tax-forecast.service`, поправь WorkingDirectory):

```
sudo cp tax-forecast.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now tax-forecast
```

Uvicorn слушает `127.0.0.1:8000`. Снаружи лучше nginx (прокси на 80/443), не открывать 8000 в интернет как есть.

### Windows (разработка)

```
cd Kursach
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Открыть http://127.0.0.1:8000  
JSON: GET /api/forecast
