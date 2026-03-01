import requests
from bs4 import BeautifulSoup
import pandas as pd
from collections import defaultdict
import dateparser
from babel.dates import format_datetime
import logging
from scrapers.common.utils_scrapper import get_random_headers, delay_between_requests  

def scrape_teatro_variedades(known_titles=None):
    """
    :param known_titles: An optional set of event names you already know.
                         If a found event is in this set, we skip further scraping.
    :return: A pandas DataFrame of events from Teatro Variedades.
    """
    logging.info("Scraping Teatro Variedades...")

    url = "https://teatrovariedades.byblueticket.pt/"
    base_url = "https://teatrovariedades.byblueticket.pt"
    session = requests.Session()  
    session.headers.update(get_random_headers())
    response = session.get(url, timeout=30)  
    if known_titles is None:
        known_titles = set()

    data = []  # list of event dicts

    if response.status_code == 200:
        soup = BeautifulSoup(response.content, 'html.parser')
        portfolio = soup.find('div', {'id': 'portfolio'})
        if not portfolio:
            raise Exception("Não foi possível encontrar a seção de portfólio no site do Teatro Variedades.")

        events = portfolio.find_all('article', class_='portfolio-item')
        seen = set()
        for event in events:
            link_element = event.find('a')
            if not link_element or 'href' not in link_element.attrs:
                continue

            link = link_element['href']
            full_link = base_url + link

            # The snippet might have the event title:
            image_element = event.find('img')
            image = image_element['src'] if image_element else 'N/A'

            name_element = event.find('span')
            if not name_element:
                continue
            name = name_element.text.strip()

            # If this event name is in known_titles, skip
            full_link_norm = str(full_link).strip().lower() 
            name_norm = str(name).strip().lower()

            if full_link_norm in seen: 
                    continue
            seen.add(full_link_norm)

            # # ✅ Correção: dedupe por URL (e fallback por nome, se vierem nomes)
            # if known_titles and (full_link_norm in known_titles or name_norm in known_titles):
            #     logging.info(f"Skipping known event: {name}")
                
            #     continue

            delay_between_requests("antes de abrir detalhe Teatro Variedades")  
            session.headers.update(get_random_headers())                        
            event_response = session.get(full_link, timeout=30)               


            # Now fetch the detail page only if not known
            event_response = requests.get(full_link)
            if event_response.status_code != 200:
                logging.warning(f"Não foi possível acessar a página do evento: {name}")
                continue

            event_soup = BeautifulSoup(event_response.content, 'html.parser')

            # ----------------------
            # Parse sessions (Horários)
            # ----------------------
            sessions = []
            table = event_soup.find('table', class_='table-hover')
            if table:
                tbody = table.find('tbody')
                if tbody:
                    rows = tbody.find_all('tr')
                    for row in rows:
                        date_time_span = row.find('span', style="color:black")
                        price_span = row.find('span', style="font-weight:bold;text-align:center;color:black")
                        if date_time_span and price_span:
                            date_time = date_time_span.text.strip()
                            price = price_span.text.strip()
                            sessions.append({'Data e Hora': date_time, 'Preço': price})

            # ----------------------
            # Parse Duration, Classification, Promoter
            # ----------------------
            duration = ''
            classification = ''
            promoter = ''
            panel_bodies = event_soup.find_all('div', class_='panel-body')
            for panel in panel_bodies:
                h5_tags = panel.find_all('h5')
                for h5 in h5_tags:
                    text = h5.text.strip()
                    if 'Duration:' in text:
                        duration = text.replace('Duration:', '').strip()
                    elif 'Classification:' in text:
                        classification = text.replace('Classification:', '').strip()
                    elif 'Promoter:' in text:
                        promoter = text.replace('Promoter:', '').strip()

            # Normalize classification
            if classification == 'To be classified+':
                classification = 'N/A'
            elif classification.endswith('+'):
                # e.g. '12+' -> 'M/12'
                age_number = classification.rstrip('+').strip()
                classification = f'M/{age_number}'

            # ----------------------
            # Parse Synopsis & Ficha Artística
            # ----------------------
            sinopse_div = event_soup.find('div', class_='sinopseSpan')
            synopsis = ''
            ficha_artistica = ''
            if sinopse_div:
                full_text = sinopse_div.get_text(separator='\n').strip()
                if 'Ficha Técnica:' in full_text or 'Ficha Técnica' in full_text:
                    parts = full_text.split('Ficha Técnica:')
                    synopsis = parts[0].strip()
                    ficha_artistica = ('Ficha Técnica:' + parts[1].strip()) if len(parts) > 1 else ''
                else:
                    synopsis = full_text

            # ----------------------
            # Dates & Times
            # ----------------------
            week_days_map = {
                'Monday': 'Segundas',
                'Tuesday': 'Terças',
                'Wednesday': 'Quartas',
                'Thursday': 'Quintas',
                'Friday': 'Sextas',
                'Saturday': 'Sábados',
                'Sunday': 'Domingos'
            }
            week_days_order = ['Segundas', 'Terças', 'Quartas', 'Quintas', 'Sextas', 'Sábados', 'Domingos']

            data_inicio = ''
            data_fim = ''
            data_extenso = ''
            horarios = ''

            if sessions:
                dates = []
                sessions_info = []
                for session in sessions:
                    date_time_str = session['Data e Hora'].strip()
                    date_time_obj = dateparser.parse(date_time_str)
                    if date_time_obj:
                        dates.append(date_time_obj)

                        day_of_week_en = date_time_obj.strftime('%A')  # e.g. Monday
                        day_of_week_pt = week_days_map.get(day_of_week_en, day_of_week_en)

                        hour_str = date_time_obj.strftime('%Hh')  # e.g. '21h'
                        sessions_info.append({
                            'date_time': date_time_obj,
                            'day_of_week': day_of_week_pt,
                            'hour': hour_str,
                            'price': session['Preço']
                        })
                    else:
                        logging.warning(f"Não foi possível analisar a data/hora: '{date_time_str}'")

                if dates:
                    dates.sort()
                    data_inicio = dates[0].strftime('%Y-%m-%d')
                    data_fim = dates[-1].strftime('%Y-%m-%d')

                    # Format 'Data Extenso' via babel
                    data_extenso = (
                        f"{format_datetime(dates[0], 'yyyy-MM-dd', locale='pt_PT').title()} a "
                        f"{format_datetime(dates[-1], 'yyyy-MM-dd', locale='pt_PT').title()}"
                    )

                # Group times by hour
                time_groups = defaultdict(list)
                for s_info in sessions_info:
                    time_groups[s_info['hour']].append(s_info['day_of_week'])

                horarios_list = []
                for hour, days in time_groups.items():
                    unique_days = sorted(set(days), key=lambda d: week_days_order.index(d))
                    if len(unique_days) == 1:
                        days_str = unique_days[0]
                    elif len(unique_days) == 2:
                        days_str = f"{unique_days[0]} e {unique_days[1]}"
                    else:
                        days_str = ', '.join(unique_days[:-1]) + f' e {unique_days[-1]}'
                    horarios_list.append(f"{days_str} às {hour}")

                horarios = '; '.join(horarios_list)
            else:
                # No sessions table found, fallback
                h3 = event.find('h3')
                data_extenso = h3.text.strip() if h3 else 'N/A'

            # ----------------------
            # Local & Concelho
            # ----------------------
            local = 'Teatro Variedades'
            concelho = 'Lisboa'

            # ----------------------
            # Prices
            # ----------------------
            prices_set = {sess['Preço'] for sess in sessions} if sessions else set()
            preco_formatado = ', '.join(prices_set) if prices_set else ''

            # ----------------------
            # Duração (minutos)
            # ----------------------
            duracao_minutos = ''.join(filter(str.isdigit, duration))  # e.g. '60'
            if duracao_minutos:
                duracao_minutos += ' Min.'
            else:
                duracao_minutos = 'N/A'

            # ----------------------
            # Append final data
            # ----------------------
            data.append({
                'Nome da Peça': name,
                'Link da Peça': full_link,
                'Imagem': image,
                'Data Início': data_inicio,
                'Data Fim': data_fim,
                'Data Extenso': data_extenso,
                'Duração (minutos)': duracao_minutos,
                'Local': local,
                'Concelho': concelho,
                'Preço Formatado': preco_formatado,
                'Promotor': promoter,
                'Sinopse': synopsis,
                'Ficha Artística': ficha_artistica,
                'Faixa Etária': classification,
                'Origem': 'Teatro Variedades',
                'Horários': horarios
            })
    else:
        raise Exception("Não foi possível acessar o site do Teatro Variedades (HTTP status != 200).")

    df = pd.DataFrame(data)
    return df

if __name__ == "__main__":
    # Example usage:
    # If we have some known event titles, we pass them. Otherwise, call with no arguments.
    known = {"Evento Antigo", "Peça X"}
    df_result = scrape_teatro_variedades(known_titles=known)
    print(df_result)