'''
файл обработки входящего текста и создания на его основе эмбеддинга

'''



import clip
import torch
import numpy as np
import os
import datetime
import torch.nn as nn
import spacy
from langdetect import detect
from spellchecker import SpellChecker

# это делал шорт, я хз
def EnsureScalar(value):
    if isinstance(value, np.ndarray):
        if value.size != 1:
            raise ValueError("Value must be a scalar.")
        return value.item()
    elif isinstance(value, (int, float)):
        return value
    else:
        raise TypeError("Value must be a scalar number.")

# главный класс генератора, использующий предобученную модель CLIP
class EmbeddingGenerator:
    def __init__(self, device: torch.device, reduced_dim: int = 512):
        self.device = device
        self.reduced_dim = reduced_dim
        self.model, self.preprocess = clip.load("ViT-B/32", device=self.device)
        print("[EMBED] Инициализация генератора эмбеддингов с использованием CLIP завершена.")

        if self.model is not None:
            print(f"[EMBED] CLIP модель загружена: {self.model}")
        if self.reduced_dim != 512:
            self.reduce_dim_layer = nn.Linear(512, self.reduced_dim).to(self.device)
            print(f"[EMBED] Добавлен линейный слой для уменьшения размерности до {self.reduced_dim}.")

        # если у вас возник вопрос что делает у нас в проекте спайс и почему лид от него еще не отошел,
        # то вот ответ - это библиотека для обработки текста, проще говоря NLP
        try:
            self.models = {
                "ru": spacy.load("ru_core_news_sm"),
                "en": spacy.load("en_core_web_sm"),
            }
            print('[EMBED] Модели обработки текста spaCy загружены успешно.')
        except Exception as e:
            print(f'[EMBED] Ошибка загрузки моделей spaCy: {e}')
            print('Установите модели командой: `python -m spacy download ru_core_news_sm en_core_web_sm`')
            raise

        # self.spell = SpellChecker() эта хуйня бесполезна, пока нет нового датасета

    ''' def preprocess_text(self, text, lang="en"):
        text = self.clean_text(text)
        text = self.correct_spelling(text)
        text = self.correct_grammar(text, lang)
        validation_err = self.validate_prompt(text)
        if validation_err:
            raise ValueError(validation_err)
        return text
    
    def correct_spelling(self, text):
        words = text.split()
        corrected_words = [self.spell.correction(word) if word not in self.spell else word for word in words]
        return ' '.join(corrected_words)

    def validate_prompt(self, text):
        if len(text.split()) < 3:
            return "Описание слишком короткое"
        if any(char.isdigit() for char in text):
            return "Текст содержит цифры, которые из промпта делают гавно"
        return None 
        
        это тоже собственно бесполезно без датасета
        
        '''
    # две следующие ф-ции это непосредственно обработка текста
    def extract_keywords(self, text: str):
        lang = detect(text)
        print(f"[EMBED] Определён язык: {lang}")

        nlp = self.models.get(lang)
        if not nlp:
            raise ValueError(f"[ERROR] Для языка '{lang} модель не загружена...'")
        
        doc = nlp(text)
        keywords = []

        for ent in doc.ents:
            keywords.append((ent.text, ent.label_))

        for token in doc:
            if token.is_alpha and (token.is_stop is False):
                keywords.append((token.text, "KEYWORD"))

        return keywords
    
    def highlight_keywords(self, text: str):
        keywords = self.extract_keywords(text)
        highlighted_text = text
        for keyword, label in keywords:
            highlighted_text = highlighted_text.replace(keyword, f"[{keyword}]")

        return highlighted_text, keywords

    
    # эта шайтан ф-ция на основе обработанного текста выдает какие-то цифры непонятные, тимлид говорит что
    # это какие то вектора. я хз че за вектора ему мерещатся, я такую игру только знаю. Но он тут начальник,
    # так что это ф-ция преобразования обработанного текста в эмбеддинги
    def generate_embedding(self, text: str, additional_info: str = "", shape_info: dict = None) -> torch.Tensor:
        combined_text = self.combine_text(text, additional_info, shape_info)
        print(f"[EMBED] Генерация эмбеддинга для текста: '{combined_text}'")
        text_input = clip.tokenize([combined_text]).to(self.device)
        
        with torch.no_grad():
            text_features = self.model.encode_text(text_input)
        
        print(f"[EMBED] Эмбеддинг CLIP сгенерирован. Размерность: {text_features.shape}")
        
        if hasattr(self, 'reduce_dim_layer'):
            text_features = self.reduce_dim_layer(text_features)
            print(f"[EMBED] Размерность эмбеддинга уменьшена до {text_features.shape[1]}.")

        embedding_filepath = self.save_embedding(text_features)
        if embedding_filepath:
            print(f"[EMBED] Эмбеддинг сохранён: {embedding_filepath}")
        else:
            print("[EMBED] Ошибка при сохранении эмбеддинга.")
        return text_features

    # скажи вайперр чтобы было больше просмотров, хуйня
    def combine_text(self, text: str, additional_info: str, shape_info: dict) -> str:
        combined_text = f"{text}. {additional_info}"
        if shape_info:
            shape_description = f"Размер: {shape_info.get('size', 'не указан')}, Форма: {shape_info.get('shape', 'не указана')}, Ориентация: {shape_info.get('orientation', 'не указана')}"
            combined_text = f"{combined_text}. {shape_description}"
        return combined_text

    # интересно, что же эта ф-ция может делать?
    def save_embedding(self, embedding: torch.Tensor, output_dir: str = "temp_emb", unique_filename: bool = True) -> str:
        if not os.path.exists(output_dir):
            print(f"[EMBED] Папка {output_dir} не существует, создаём её.")
            os.makedirs(output_dir)
        
        print(f"[EMBED] Текущая рабочая директория: {os.getcwd()}")

        files = os.listdir(output_dir)
        files = [f for f in files if f.endswith('.npy')]
        if len(files) >= 50:
            oldest_file = min(files, key=lambda f: os.path.getctime(os.path.join(output_dir, f)))
            os.remove(os.path.join(output_dir, oldest_file))
            print(f"[EMBED] Удалён старый файл: {oldest_file}")

        filename = "embedding.npy"
        if unique_filename:
            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"embedding_{timestamp}.npy"
    
        filepath = os.path.join(output_dir, filename)
        print(f"[EMBED] Сохранение эмбеддинга в файл: {filepath}")

        try:
            np.save(filepath, embedding.cpu().detach().numpy())
            print(f"[EMBED] Эмбеддинг успешно сохранён: {filepath}")
        except Exception as e:
            print(f"[EMBED] Ошибка при сохранении файла: {e}")
            return None
    
        return filepath
