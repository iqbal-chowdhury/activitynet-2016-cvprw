import json

from keras.utils.generic_utils import Progbar
from work.dataset.dataset import AbstractDataset, AbstractInstance


class ActivityNetDataset(AbstractDataset):

    def __init__(self, videos_path, labels_path, stored_videos_path=None, files_extension=None):
        super(ActivityNetDataset, self).__init__()
        with open(videos_path, 'r') as dataset_file:
            self.database = json.load(dataset_file)
        self._import_labels(labels_path)

        self.version = 'v1.3_cleaned'

        self.stored_videos_path = stored_videos_path
        self.files_extension = files_extension

        self.videos = []
        for v_id in self.database.keys():
            self.videos.append(ActivityNetVideo(
                self,
                v_id,
                self.database[v_id],
                path=self.stored_videos_path
            ))

        self.instances_training = []
        self.instances_validation = []
        self.instances_testing = []
        self.class_weights = None

    def _import_labels(self, labels_path):
        with open(labels_path, 'r') as f:
            lines = f.readlines()
        self.labels = []
        for l in lines:
            l = l.strip().split('\t')
            self.labels.append((int(l[0]), l[1]))

    def generate_instances(self, size=(128, 171), length=16,
            overlap=0):
        """ Method to generate all the instances for training this dataset.
        This instances will be generated by the videos stored and some
        parameters that will be given.
        This will generate the instances of all subsets.
        """
        self.size = size
        self.length = length
        self.instances_training = []
        self.instances_validation = []
        self.instances_testing = []
        progbar = Progbar(len(self.videos))
        count = 0
        progbar.update(0)
        for video in self.get_subset_videos('training'):
            self.instances_training += video.get_video_instances(
                length=length,
                overlap=overlap
            )
            count += 1
            if count % 100 == 0:
                progbar.update(count)
        for video in self.get_subset_videos('validation'):
            self.instances_validation += video.get_video_instances(
                length=length,
                overlap=overlap
            )
            count += 1
            if count % 100 == 0:
                progbar.update(count)
        for video in self.get_subset_videos('testing'):
            self.instances_testing += video.get_video_instances(
                length=length,
                overlap=overlap
            )
            count += 1
            if count % 100 == 0:
                progbar.update(count)
        progbar.update(count)

    @property
    def instances(self):
        return self.instances_training + self.instances_validation + self.instances_testing

    @property
    def num_classes(self):
        return len(self.labels)

    def get_output_index(self, label):
        """ For the label given returns the index of the label.
        """
        return self.get_labels().index(label)

    def get_subset_videos(self, subset):
        """ Returns the videos corresponding to the given subset: training,
        validation or testing.
        """
        return [video for video in self.videos \
            if video.subset == subset]

    def get_labels(self):
        """ Returns the labels for all the videos
        """
        return [x[1] for x in self.labels]

    def get_labels_indx(self):
        """ Returns the labels for all the videos
        """
        return [x[0] for x in self.labels]

    def get_stats(self):
        """ Return a descriptive stats of all the videos available in the
        dataset.
        """
        return {
            'videos': {
                'total': len(self.database.keys()),
                'training': len(self.get_videos('training')),
                'validation': len(self.get_videos('validation')),
                'testing': len(self.get_videos('testing'))
            },
            'labels': {
                'total': len(self.labels),
                'leaf_nodes': len(self.get_labels())
            }
        }

    def get_videos(self, subset):
        return [video for video in self.videos \
            if video.subset == subset]

    def get_videos_from_label(self, label, input_videos=None):
        if input_videos is None:
            input_videos = self.videos
        return [video for video in input_videos if video.label == label]

    def get_total_duration(self):
        duration = 0
        for video in self.videos:
            duration += video.duration
        return duration

    def get_activity_duration(self, activity=None):
        videos = []
        if activity is None:
            videos = self.videos
        else:
            videos = self.get_videos_from_label(activity)

        duration = 0
        for video in videos:
            duration += video.get_activity_duration()
        return duration

    def compute_class_weights(self):
        if self.class_weights:
            print('Already computed class weights')
            return self.class_weights

        if not self.instances_training:
            raise Exception('It is required to have generated training ' +
                            ' instances to compute class weights.')

        self.class_weights = {}
        total_instances = len(self.instances_training)
        for indx in self.get_labels_indx():
            instances = [ins for ins in self.instances_training if ins.output == int(indx)]
            weight = 1. - float(len(instances))/total_instances
            self.class_weights.update({indx: weight})
        return self.class_weights

class ActivityNetVideo(object):
    """ Class to encapsulate a video from the given dataset
    """
    def __init__(self, dataset, video_id, params, path=None, extension='mp4'):
        self.dataset = dataset
        self.video_id = video_id
        self.url = params['url']
        self.subset = params['subset']
        self.resolution = params['resolution']
        self.duration = params['duration']
        self.annotations = params['annotations']
        self.label = None

        self.path = path
        self.extension = extension
        self.num_frames = params['num_frames']
        self.output_type = 'category'


        if self.annotations != []:
            self.label = self.annotations[0]['label']

    def get_activity(self):
        return self.label

    def get_activity_duration(self):
        duration = 0
        for annotation in self.annotations:
            duration += annotation['segment'][1] - \
                annotation['segment'][0]
        return duration

    def get_video_instances(self, length, overlap):
        """ Generates the video instances referring to this ActivityNetDataset
        videos. This instances are chunks of videos with the given size and
        length overlaping each other the proportion given.
        # Arguments
            size (tuple(int)): Size of the video frames for the instances
            length (int): temporal length of the video instances. Given as
                number of frames.
            overlap (float): proportion of the overlaping between video
                instances.
        """
        assert overlap >= 0 and overlap <1


        # Generate the list with the index of the first frame for each instance
        last_first_frame = self.num_frames - length
        overlap_fr = int(overlap*length)
        if overlap_fr == length:
            raise Exception('The overlap is 100%% of the frames and have no \
                sense.')
        start_frames = range(0, last_first_frame, length-overlap_fr)

        # Check the output for each frame of the video
        outputs = ['none'] * self.num_frames
        for i in range(self.num_frames):
            # Pass frame to temporal
            t = i / float(self.num_frames) * self.duration
            for annotation in self.annotations:
                if t > annotation['segment'][0] and t < annotation['segment'][1]:
                    outputs[i] = self.label
                    break

        instances = []
        for start_frame in start_frames:
            # Obtain the label for this instance and then its output
            output = None
            if self.label:
                outs = outputs[start_frame:start_frame+length]
                if outs.count(self.label) >= length/2:
                    output = self.dataset.get_output_index(self.label)
                else:
                    output = self.dataset.get_output_index('none')

            instances.append(ActivityNetInstance(
                instance_id=self.video_id,
                start_frame=start_frame,
                output=output
            ))
        return instances


class ActivityNetInstance(AbstractInstance):

    def __init__(self, instance_id, start_frame, output):
        super(ActivityNetInstance, self).__init__(instance_id, output)
        self.start_frame = start_frame
