class stage_position:
    def __init__(self,x,y,z):
        self.x = x
        self.y = y
        self.z = z
        

def load_pos_file(filepath,studio,bridge):
    java_file = bridge.construct_java_object('java.io.File', args=[filepath])
    position_list_manager = studio.get_position_list_manager()
    postition_list = position_list_manager.get_position_list()
    postition_list.load(java_file)
    nb_positions = postition_list.get_number_of_positions()
    position_list = []
    for i in range(nb_positions):
        position = postition_list.get_position(i)
        x = position.get_x()
        y = position.get_y()
        z = position.get_z()
        pos = stage_position(x,y,z)
        position_list.append(pos)
    return position_list


def get_pos_from_mm(studio):
    position_list_manager = studio.get_position_list_manager()
    postition_list = position_list_manager.get_position_list()
    nb_positions = postition_list.get_number_of_positions()
    position_list = []
    for i in range(nb_positions):
        position = postition_list.get_position(i)
        x = position.get_x()
        y = position.get_y()
        z = position.get_z()
        pos = stage_position(x,y,z)
        position_list.append(pos)
    return position_list


