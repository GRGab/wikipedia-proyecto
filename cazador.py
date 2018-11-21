import requests
import json
from collections import deque
import numpy as np
from matplotlib import pyplot as plt
from datetime import datetime
import time

class CazadorDeDatos():
    def __init__(self, language='en', fmt='json', data_limit=500,
                 generator_limit=5):
        self.language = language
        self.format = fmt
        self.data_limit = data_limit
        self.generator_limit = generator_limit
        # actiondict es el dict con parámetros que se usan siempre
        self.actiondict = self.set_actiondict()

    def set_actiondict(self):
        actiondict = {'action': 'query',
                      'format': self.format,
                      'redirects': ''}
        # Para que el formato sea el correcto:
        if actiondict['format'] in ['json', 'php']:
            actiondict['formatversion'] = '2'
        return actiondict

    def set_limits(self, pedido):
        if 'cmtitle' in pedido.keys():
            pedido['cmlimit'] = self.data_limit
        if 'generator' in pedido.keys():
            if pedido['generator'] == 'links':
                pedido['gpllimit'] = self.generator_limit
            if pedido['generator'] == 'categorymembers':
                pedido['gcmlimit'] = self.generator_limit
        if 'prop' in pedido.keys():
            if 'links' in pedido['prop']:
                pedido['pllimit'] = self.data_limit
            if 'categories' in pedido['prop']:
                pedido['cllimit'] = self.data_limit
        return pedido

    def query(self, pedido, verbose=True):
        pedido = pedido.copy()
        pedido.update(self.actiondict)
        # Seteamos los límites
        pedido = self.set_limits(pedido)
        # Comenzamos las llamadas a la API
        lastContinue = {}
        acc = 0
        while True:
            acc += 1
            # Clone original request
            pedido2 = pedido.copy()
            # Modify it with the values returned in the 'continue' section of the last result.
            pedido2.update(lastContinue)
            # Call API
            result = requests.get('https://{}.wikipedia.org/w/api.php'.format(self.language),
                                params=pedido2).json()
            if 'error' in result:
                # Mepa que no queremos que se eleve un error porque eso
                # interrumpe la ejecución
                # raise Exception(result['error'])
                print('ERROR:', result['error'])
            if 'warnings' in result:
                print(result['warnings'])
            if 'query' in result:
                r = result['query']
                if verbose and 'pages' in r.keys():
                    print('# de páginas adquiridas: ', len(r['pages']))
                    print('# de links adquiridos:', count_items(r)[1])
            if verbose and 'batchcomplete' in result and result['batchcomplete']==True:
                print('Batch completo!')
            if 'query' in result:
                yield r
            if 'continue' not in result:
                break
            lastContinue = result['continue']
        if verbose:
            print('# de llamadas a la API:', acc)
    
    def get_pagesincat(self, category_name, props, data=None,
                            verbose=True, query_verbose=False):
        """
        Para cada página perteneciente a la categoría `category_name`, obtiene
        las propiedades dadas por la lista 'props' y las agrega a la información
        contenida en el diccionario 'data'. Si data == None, se parte de un dict
        vacío.

        Propiedades implementadas: links, categories.
        """
        prop = '|'.join(props)
        pedido = {'generator': 'categorymembers',
                  'gcmtitle': category_name,
                  'gcmtype': 'page',
                  'prop': prop}
        # Si se provee el dict 'data', queremos copiarlo
        # para no modificar el input inplace.
        if data is None:
            data = {}
        else:
            data = data.copy()
        # Set de todas las categorías encontradas
        set_of_cats = set()
        # Llamadas a la API, guardamos los resultados
        for result in self.query(pedido, verbose=query_verbose):
            self.update_data(result, data, set_of_cats)
        if verbose:
            print('# de páginas en la categoría:', len(data.keys()))
            n_links = sum(len(data[title]['links']) for title in data.keys())
            print('# de links obtenidos en total:', n_links)
        return data, set_of_cats

    def update_data(self, result, data, set_of_cats=None):
        """
        Guarda los datos correspondientes a las propiedades que
        resultan de una llamada a la API dentro de un diccionario 'data'
        definido previamente, sin sobreescribir lo que ya estaba.
        Opcionalmente, si se le da un conjunto 'set_of_cats', guarda allí
        los nombres de todas las categorías encontradas en dicha llamada.

        Propiedades implementadas: links, categories.
        """
        pages = result['pages']
        n_pages_temp = len(pages)
        for i in range(n_pages_temp):
            title = pages[i]['title']
            # Si la página ya fue visitada antes, entonces
            # no queremos volver a guardar esa información
            if title not in data.keys():
                # dict para que guarde allí la info
                data[title] = {'links': [], 'categories': []}
            if 'links' in pages[i].keys():
                if 'links' not in data[title].keys():
                    data[title]['links'] = []
                linknames = [d['title'] for d in pages[i]['links']]
                data[title]['links'] += linknames
            if 'categories' in pages[i].keys():
                if 'categories' not in data[title].keys():
                    data[title]['categories'] = []
                catnames = [d['title'] for d in pages[i]['categories']]
                data[title]['categories'] += catnames
                if set_of_cats is not None:
                    set_of_cats.update(set(catnames))
            if 'text' in pages[i].keys():
                ### NO IMPLEMENTADO AÚN ###
                if 'text' not in data[title].keys():
                    pass

    def get_cat_data(self, root_category, props, maxpages=0, verbose=True):
        """
        Dada la categoría 'root_category' de Wikipedia, extrae las propiedades
        de la lista 'props' para todas las páginas que pertenecen a la misma.
        'maxpages' es el nro. máximo de páginas a obtener; si vale 0 o menos
        entonces no hay máximo.
        Output:
            data : dict
                Diccionario de pares página : información.
            set_of_cats : set
                Conjunto de nombres de categorías que aparecen en todas las
                páginas visitadas.

        Propiedades implementadas: links, categories.
        """
        ### Estructuras auxiliares
        # Cola de espera o 'queue' para implementar el BFS (Breadth-First Search)
        queue = deque()
        # Conjunto de categorías ya visitadas
        visited = set()
        # Diccionario de pares categoría : lista de subcategorías
        children = {}

        ### Inicialización
        queue.append(root_category)
        queue.append('<<END_OF_LEVEL>>')
        # Estructuras que acumulan la información
        data = {}
        set_of_cats = set()
        cat_tree = {}
        # Contadores
        ncats_visited = 0
        nlevels = 0

        # Usamos un mecanismo de contadores "end of level" en la cola para saber cuándo
        # cambiamos de nivel de búsqueda. Cuando termine el recorrido, quedará un contador
        # en la cola y se verificará len(queue) == 1.

        while len(queue) > 1:

            # Extraemos la primera categoría de la cola
            cat_actual = queue.popleft()
            # Si es un marcador de "end of level", sumamos 1 al contador,
            # agregamos un marcador "end of level" a la cola y sacamos
            # un ítem más
            if cat_actual == '<<END_OF_LEVEL>>':
                if verbose: print('END OF LEVEL')
                nlevels += 1
                queue.append('<<END_OF_LEVEL>>')
                cat_actual = queue.popleft()

            # La 'visitamos'
            if verbose: print(ncats_visited)
            data_t, set_of_cats_t = self.get_pagesincat(cat_actual, props,
                                                             data=data,
                                                             verbose=verbose)
            data.update(data_t)
            set_of_cats.update(set_of_cats_t)
            ncats_visited += 1

            # Agregamos las subcategorías de la categoría actual a la cola
            # y a children[cat_actual] como una lista.
            pedido_subcats = {'generator': 'categorymembers',
                              'gcmtitle': cat_actual,
                              'gcmtype': 'subcat'}
            children[cat_actual] = []
            for result in self.query(pedido_subcats, verbose=False):
                pages = result['pages']
                for i in range(len(pages)):
                    subcat = pages[i]['title']
                    children[cat_actual].append(subcat)
                    # Solo agregamos la subcat si no está en la cola aún
                    # ni fue procesada ya.
                    if subcat not in visited and subcat not in queue:
                        queue.append(subcat)
            
            # Terminamos de procesar la categoría actual
            visited.add(cat_actual)

            # Si ya visitamos suficientes páginas, nos detenemos
            if maxpages > 0 and len(data.keys()) > maxpages:
                break

        if verbose:
            print('------------------------------')
            print('# categorías visitadas:', ncats_visited)
            print('# páginas visitadas:', len(data.keys()))
            print('# niveles recorridos:', nlevels)
        return data, set_of_cats, children
    
   

    def get_cat_tree(self, category_name, verbose=True):
        """
        Función recursiva que intenta obtener el árbol de categorías
        partiendo de una categoría raíz. Las categorías de Wikipedia
        no conforman un árbol. Esto quiere decir que puede haber
        nodos repetidos y podría llegar a fallar la ejecución debido
        a un loop infinito.

        Returns
        -------
        tree : dict
            Diccionarios anidados con la estructura de las categorías
        n_l : int
            Número de llamadas realizadas a la función get_cat_tree
        """
        print('Comienza una llamada')
        pedido = {'generator': 'categorymembers',
                  'gcmtitle': category_name,
                  'gcmtype': 'subcat'}
        tree = {category_name: {}}
        n_l = 1
        for result in self.query(pedido, verbose=False):
            pages = result['pages']
            for i in range(len(pages)):
                subcat = pages[i]['title']
                # Si ya pasamos por esta categoría en este nivel
                # del árbol, entonces no hacemos nada.
                if subcat not in tree.keys():
                    subtree, n_l_rec = self.get_cat_tree(subcat, verbose=verbose)
                    tree[category_name].update(subtree)
                    n_l += n_l_rec
        print('Termina una llamada. # subcats:', len(tree[category_name].keys()))
        return tree, n_l
                
####################################
# Funciones por fuera de la clase
####################################

def count_items(query_result):
    """
    Función auxiliar que te tira cuántas páginas y cuántos links hay
    en un dado result
    """
    pages = query_result['pages']
    n_pages = len(pages)
    get_links = lambda dic: dic['links'] if 'links' in dic.keys() else []
    n_links_perpage = [len(get_links(pages[i])) for i in range(n_pages)]
    n_links_tot = sum(n_links_perpage)
    return n_pages, n_links_tot

def curate_links(data):
    data = data.copy()
    n_eliminated = 0
    for title in data.keys():
        linklist = data[title]['links']
        n_i = len(linklist)
        # Los links no deben comenzar con uno de estos prefijos.
        bad_prefixes = ["Wikipedia:", "Category:", "Template:",
                        "Template talk:", "Help:", "Portal:", "Book:"] 
        # Chequeamos dicha condición mediante una función
        condition = lambda l: all(not l.startswith(pref) for pref in bad_prefixes)
        # Aplicamos la función como filtro
        linklist = [l for l in linklist if condition(l)]
        n_f = len(linklist)
        data[title]['links'] = linklist
        n_eliminated += n_i - n_f
    print('# de links malos eliminados:', n_eliminated)
    return data

    
def lista_de_timestamps(pedido):
    '''Para un pedido a la API en un intervalo de tiempos, me hago una lista
    en los timestamps de las rewiews en formato UNIX.'''
    data =[]
    for i in pedido:
        data.append(i)
    lista =[]
    for j in range(len(data[0]['pages'][0]['revisions'])):
       a = data[0]['pages'][0]['revisions'][j]['timestamp']
       b = time.mktime(datetime.strptime(a, '%Y-%m-%dT%XZ').timetuple())
       lista.append(b)
    return lista


def elegir_timestamp(pedido, ref_time, delta_lim = 2592000):
    '''Dado un timestamp de referencia en el formato que trabaja
    la API, elige de una lista de timestamp el 
    mas cercano y lo devuelve a la salida el tiempo mas cercano.
    Si el timestamp mas cercano se encuentra a una distancia delta_lim del
    tiempo pedido (por default 30 dias), la funcion arroja un None'''
    
    #Paso la fecha de referencia a sistema horario unix, mas facil.
    #de manipular.
    ref_time_unix = time.mktime(datetime.strptime(ref_time, '%Y-%m-%dT%XZ').timetuple())
    
    lista = lista_de_timestamps(pedido) 
    valor_elegido_unix = min(lista, key=lambda x:abs(x-ref_time_unix))
    
    #Me fijo a que distancia esta el valor seleccionado del que pedi.
    delta = abs(valor_elegido_unix - ref_time_unix)
    if (delta < delta_lim):
        valor_elegido = datetime.utcfromtimestamp(
                valor_elegido_unix).strftime('%Y-%m-%dT%XZ')
    else:
        valor_elegido = None
    return valor_elegido


#%%
if __name__ == '__main__':
    # Inicializamos objeto
    caza = CazadorDeDatos()

    #%% Pruebas de get_pagesincat
    data_1, cats = caza.get_pagesincat(
        'Category:Zwitterions',
#        'Category:Ions',
#        'Category:Interaction',
#        'Category:Physics',
         ['links', 'categories']
            )
    data_1 = curate_links(data_1)
    
    #%% Pruebas de get_cat_data
    data, cats, children = caza.get_cat_data(
         'Category:Zwitterions',
#        'Category:Ions',
#        'Category:Interaction',
#        'Category:Physics',
         ['links', 'categories'],
         maxpages=100
        )
    data = curate_links(data)
    
    #%% Pruebas de get_cat_tree

    # ### Árbol súper chico de categorías
#    arbol, n_l = caza.get_cat_tree('Category:Zwitterions')
    ### Árbol no tan chico
    arbol, n_l = caza.get_cat_tree('Category:Ions')
    ### Árbol más grande
#    arbol, n_l = caza.get_cat_tree('Category:Interaction')

#%%
#    # Ejemplos de búsquedas que se pueden realizar mediante el método query
#    # Los objetos resultantes son generadores, i.e. al ejecutar este código,
#    # no se realiza ninguna llamada a la API sino que eso se posterga hasta
#    # que se itere sobre alguno de los objetos.
#    res1 = caza.query({'list': 'categorymembers', 'cmtype': 'page', 'cmtitle': 'Category:Physics'})
#    res2 = caza.query({'titles': 'Main page'})
#    res3 = caza.query({'titles': 'Physics', 'prop': 'links'})
#    res4 = caza.query({'titles': 'Physics', 'prop': 'links', 'generator': 'links'})
    res5 = caza.query({'gcmtitle': 'Category:Physics',
                       'prop': 'links',
                       'generator': 'categorymembers',
                       'gcmtype': 'page'
                       })
#    res6 = caza.query({'gcmtitle': 'Category:Physics',
#                       'generator': 'categorymembers',
#                       'gcmtype': 'subcat'
#                       })
#%%  
    
    res7 = caza.query({'titles': 'Higgs Boson',              
                          'prop':'revisions',
                          'rvprop':'timestamp',
                          'rvlimit':"max",
                          'rvstart':'2012-07-05T12:00:00Z',
                          'rvend':'2012-08-25T23:59:00Z',
                          'rvdir':'newer'
                          })
                
    numero = elegir_timestamp(res7, '2012--25T23:59:00Z')
    
    
#%%
    pedido = res7
    data =[]
    for i in pedido:
        data.append(i)
    print (data)
    
        #%%
    lista =[]
    for j in range(len(data[0]['pages'][0]['revisions'])):
       a = data[0]['pages'][0]['revisions'][j]['timestamp']
       a = time.mktime(datetime.strptime(a, '%Y-%m-%dT%XZ').timetuple())
       print(a)

