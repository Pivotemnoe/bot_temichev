-- Добавление расширенных полей для питомцев (Pets v2)

ALTER TABLE pets ADD COLUMN birth_year INTEGER;
ALTER TABLE pets ADD COLUMN birth_month INTEGER;
ALTER TABLE pets ADD COLUMN birth_day INTEGER;
ALTER TABLE pets ADD COLUMN birth_precision TEXT;  -- 'day' | 'month' | 'year' | 'unknown'

ALTER TABLE pets ADD COLUMN sex TEXT;              -- свободный текст: "самец", "самка", "не указано" и т.п.
ALTER TABLE pets ADD COLUMN weight_kg REAL;        -- вес в килограммах
ALTER TABLE pets ADD COLUMN breed TEXT;            -- порода