import json
import boto3
import re

AMI_PATTERN = re.compile("jenkins-win-slave*")  # The pattern to match AMIs to
NUMBER_TO_RETAIN = 2  # Number of non-tagged AMIs to retain
ACCOUNT_IDS = ['524624737625']  # List of accounts to check for AMIs


class Image:
    """ Helper class for AMI images
    """

    def __init__(self, name, created, tags, id, snapshots):
        self.name = name
        self.created = created
        self.tags = tags
        self.id = id
        self.snapshots = snapshots
        self.delete = True

    def __str__(self):
        return 'Image: ' + self.name + self.created + str(self.delete)

    def __repr__(self):
        return 'Image: ' + self.name + self.created + str(self.delete)


def get_slave_images(response):
    """ Return a list of lists of the required attributes of all images from
        a boto3 generated describe_images response.
    """
    slaveAmis = []
    for image in response:
        snapshots = []
        if re.match(AMI_PATTERN, image["Name"]):
            if ("Tags" not in image):
                image["Tags"] = []
            for bdm in image["BlockDeviceMappings"]:
                if "Ebs" in bdm:
                    snapshots.append(bdm["Ebs"]["SnapshotId"])
            slaveAmis.append(Image(image["Name"],
                                   image["CreationDate"],
                                   image["Tags"],
                                   image["ImageId"],
                                   snapshots))
    return slaveAmis


def remove_tagged_images(imageList):
    """ Remove from a given list of Image objects any images with the tag
        'Retain' present
    """
    untaggedList = []
    for image in imageList:
        tagged = False
        for tag in image.tags:
            if tag["Key"] == "Retain":
                tagged = True
        if tagged == False:
            untaggedList.append(image)
    return untaggedList


def mark_newest_images(imageList, numberToRetain):
    """ Given a list of images, Set the delete attribute of the image to
        False if it is one of the numberToRetain-th newest
    """
    sortedList = sorted(imageList,
                        reverse=True,
                        key=lambda image: image.created)
    for x in range(0, numberToRetain):
        sortedList[x].delete = False
    return sortedList


def delete_old_images(imageList):
    """ Delete any AMIs marked for deletion, along with their associated
        snapshots
    """
    ec2 = boto3.client('ec2')
    amisToDelete = []
    snapshotsToDelete = []
    for image in imageList:
        if image.delete == True:
            amisToDelete.append(image.id)
            for snapshot in image.snapshots:
                snapshotsToDelete.append(snapshot)
    for ami in amisToDelete:
        ec2.deregister_image(
            ImageId=ami
        )
    for snapshot in snapshotsToDelete:
        ec2.delete_snapshot(
            SnapshotId=snapshot
        )


def lambda_handler(event, context):
    ec2 = boto3.client('ec2')

    for account_id in ACCOUNT_IDS:
        response = ec2.describe_images(
            Owners=[account_id]
        )["Images"]

        slaveImages = get_slave_images(response)
        slaveImages = remove_tagged_images(slaveImages)
        slaveImages = mark_newest_images(slaveImages, NUMBER_TO_RETAIN)
        delete_old_images(slaveImages)
    return {
        'statusCode': 200,
        'body': ""
    }
