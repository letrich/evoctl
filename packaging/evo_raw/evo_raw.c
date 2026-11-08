// SPDX-License-Identifier: GPL-2.0+
/*
 * evo_raw - concurrent control-transfer access for Audient EVO interfaces
 *
 * The helper binds only the unused DFU interface (3). It submits endpoint-zero
 * control requests from inside the kernel, while snd-usb-audio keeps ownership
 * of AudioControl and both streaming interfaces.
 *
 * Design derived from vanzaho/audient-evo-py, released into the public domain.
 */

#include <linux/fs.h>
#include <linux/kref.h>
#include <linux/miscdevice.h>
#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/slab.h>
#include <linux/uaccess.h>
#include <linux/usb.h>

#define AUDIENT_VENDOR_ID 0x2708
#define EVO8_PRODUCT_ID 0x0007
#define EVO_DFU_INTERFACE 3
#define EVO_MAX_DATA 256

struct evo_ctrl_xfer {
  __u8 request_type;
  __u8 request;
  __u16 value;
  __u16 index;
  __u16 length;
  __u8 data[EVO_MAX_DATA];
};

#define EVO_CTRL_TRANSFER _IOWR('E', 0, struct evo_ctrl_xfer)

struct evo_device {
  struct usb_device *udev;
  struct miscdevice misc;
  struct mutex lock;
  struct kref reference;
};

static void evo_delete(struct kref *reference) {
  struct evo_device *device =
      container_of(reference, struct evo_device, reference);

  kfree(device);
}

static int evo_open(struct inode *inode, struct file *file) {
  struct evo_device *device =
      container_of(file->private_data, struct evo_device, misc);

  kref_get(&device->reference);
  file->private_data = device;
  return 0;
}

static int evo_release(struct inode *inode, struct file *file) {
  struct evo_device *device = file->private_data;

  kref_put(&device->reference, evo_delete);
  return 0;
}

static long evo_ioctl(struct file *file, unsigned int command,
                      unsigned long argument) {
  struct evo_device *device = file->private_data;
  struct evo_ctrl_xfer transfer;
  unsigned int pipe;
  void *buffer;
  int result;

  if (command != EVO_CTRL_TRANSFER)
    return -ENOTTY;
  if (copy_from_user(&transfer, (void __user *)argument, sizeof(transfer)))
    return -EFAULT;
  if (!transfer.length || transfer.length > EVO_MAX_DATA)
    return -EINVAL;

  buffer = kmalloc(transfer.length, GFP_KERNEL);
  if (!buffer)
    return -ENOMEM;
  if (!(transfer.request_type & USB_DIR_IN))
    memcpy(buffer, transfer.data, transfer.length);

  mutex_lock(&device->lock);
  if (!device->udev) {
    result = -ENODEV;
    goto unlock;
  }

  pipe = transfer.request_type & USB_DIR_IN
             ? usb_rcvctrlpipe(device->udev, 0)
             : usb_sndctrlpipe(device->udev, 0);
  result = usb_control_msg(device->udev, pipe, transfer.request,
                           transfer.request_type, transfer.value,
                           transfer.index, buffer, transfer.length, 1000);

  if (result >= 0 && transfer.request_type & USB_DIR_IN) {
    memcpy(transfer.data, buffer, result);
    transfer.length = result;
    if (copy_to_user((void __user *)argument, &transfer, sizeof(transfer)))
      result = -EFAULT;
  }

unlock:
  mutex_unlock(&device->lock);
  kfree(buffer);
  return result;
}

static const struct file_operations evo_operations = {
    .owner = THIS_MODULE,
    .open = evo_open,
    .release = evo_release,
    .unlocked_ioctl = evo_ioctl,
};

static int evo_probe(struct usb_interface *interface,
                     const struct usb_device_id *id) {
  struct usb_device *udev = interface_to_usbdev(interface);
  struct evo_device *device;
  int result;

  if (interface->cur_altsetting->desc.bInterfaceNumber != EVO_DFU_INTERFACE)
    return -ENODEV;

  device = kzalloc(sizeof(*device), GFP_KERNEL);
  if (!device)
    return -ENOMEM;

  mutex_init(&device->lock);
  kref_init(&device->reference);
  device->udev = usb_get_dev(udev);
  device->misc.minor = MISC_DYNAMIC_MINOR;
  device->misc.name = "evo8";
  device->misc.fops = &evo_operations;
  device->misc.parent = &interface->dev;

  result = misc_register(&device->misc);
  if (result) {
    usb_put_dev(device->udev);
    kref_put(&device->reference, evo_delete);
    return result;
  }

  usb_set_intfdata(interface, device);
  dev_info(&interface->dev, "concurrent control registered at /dev/evo8\n");
  return 0;
}

static void evo_disconnect(struct usb_interface *interface) {
  struct evo_device *device = usb_get_intfdata(interface);
  struct usb_device *udev;

  usb_set_intfdata(interface, NULL);
  if (!device)
    return;

  misc_deregister(&device->misc);
  mutex_lock(&device->lock);
  udev = device->udev;
  device->udev = NULL;
  mutex_unlock(&device->lock);
  usb_put_dev(udev);
  kref_put(&device->reference, evo_delete);
}

static const struct usb_device_id evo_devices[] = {
    {USB_DEVICE(AUDIENT_VENDOR_ID, EVO8_PRODUCT_ID)},
    {},
};
MODULE_DEVICE_TABLE(usb, evo_devices);

static struct usb_driver evo_driver = {
    .name = "evo_raw",
    .id_table = evo_devices,
    .probe = evo_probe,
    .disconnect = evo_disconnect,
};
module_usb_driver(evo_driver);

MODULE_LICENSE("GPL");
MODULE_AUTHOR("evoctl contributors");
MODULE_DESCRIPTION("Concurrent control transfer access for Audient EVO 8");
