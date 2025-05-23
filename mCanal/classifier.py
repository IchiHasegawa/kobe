#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import datetime
from pathlib import Path
from skimage.io import imsave, imread

import torch
import torch.nn as nn
import torch.utils.data
import torchvision
from torch.utils.tensorboard import SummaryWriter
from torchmetrics.classification import F1Score, Recall, Precision, AUROC

from utils.loader import load_dataset, XpDataset

from torch.nn.functional import softmax

device = 'cuda:0' if torch.cuda.is_available() else 'cpu'


def load_base_model(path: Path, out_features: int) -> nn.Module:
    net = torchvision.models.vgg16()
    net.classifier[6] = nn.Sequential(
        nn.Linear(
            in_features=net.classifier[6].in_features,
            out_features=out_features,
            bias=True
        ),
        nn.Sigmoid()
    )
    net.load_state_dict(torch.load(path))

    # print(net)

    # Remove classification layers = copy except last layer
    # net = torch.nn.Sequential(*(list(net.children())[:-1]))
    net = net.features
    return net

def exec_training(
        root: Path,
        annotation: Path,
        split: Path,
        label: str,
        work_root: Path
):
    transform = torchvision.transforms.Compose([
        #torchvision.transforms.Resize((224, 224), torchvision.transforms.InterpolationMode.BILINEAR),
        # torchvision.transforms.Normalize(0.5, 0.5),
        # torchvision.transforms.ToTensor(),
        torchvision.transforms.ConvertImageDtype(torch.float32),
        torchvision.transforms.RandomRotation(
            (-180, 180),
            torchvision.transforms.InterpolationMode.BILINEAR,
            expand=True
        ),
        torchvision.transforms.RandomHorizontalFlip(0.25),
        torchvision.transforms.RandomVerticalFlip(0.25),
        torchvision.transforms.Resize(
            (224, 224),
            torchvision.transforms.InterpolationMode.BILINEAR
        ),
        torchvision.transforms.Normalize(
            mean=(2047.5, 2047.5, 2047.5),
            std=(2047.5, 2047.5, 2047.5)
        )
    ])

    # Load data list
    train_list, valid_list, test_list = load_dataset(
        root=root, annotation=annotation, split=split
    )

    train_dataset = XpDataset(label=label, data=train_list, transform=transform)

    valid_dataset = XpDataset(label=label, data=valid_list, transform=transform)
    #test_dataset = XpDataset(label=label, data=test_list, transform=transform)
    num_classes = train_dataset.c

    # Init data loaders
    train_loader = torch.utils.data.DataLoader(
        train_dataset, batch_size=32, shuffle=True,
        num_workers=os.cpu_count() // 2, pin_memory=True
    )
    valid_loader = torch.utils.data.DataLoader(
        valid_dataset, batch_size=32, shuffle=True,
        num_workers=os.cpu_count() // 2, pin_memory=True
    )
    #test_loader = torch.utils.data.DataLoader(
    #    test_dataset, batch_size=batch_size, shuffle=True,
    #    num_workers=os.cpu_count() // 2, pin_memory=True
    #)

    # Init model
    net = torchvision.models.vgg16_bn(weights=torchvision.models.VGG16_BN_Weights)
    # Replace output layer for multi-class classification
    net.classifier[6] = nn.Sequential(
        nn.Linear(
            in_features=net.classifier[6].in_features,
            out_features=num_classes,
            bias=True
        ),
        #nn.Softmax()
        nn.Sigmoid()
    )
    net.to(device)
    #print(net)

    epochs = 600
    #optimizer = torch.optim.RAdam(net.parameters())
    optimizer = torch.optim.Adam(net.parameters(), lr=1e-4)
    criterion = nn.BCELoss()
    #criterion = nn.BCEWithLogitsLoss()
    # metrics
    f1 = F1Score(task="binary", num_classes=num_classes).to(device)
    #f1 = BinaryF1Score(threshold=0.5).to(device)
    recall = Recall(task="binary", threshold=0.5, num_classes=num_classes).to(device)
    precision = Precision(task="binary", average='macro', num_classes=num_classes).to(device)
    auroc = AUROC(task="binary", average='macro', num_classes=num_classes).to(device)

    # Temporary working directory
    workdir = work_root / datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
    workdir.mkdir(parents=True, exist_ok=True)
    # Logging by TensorBoard
    logger = SummaryWriter(log_dir=str(workdir))

    for epoch in range(epochs):
        print(f"Epoch [{epoch:5}/{epochs:5}]")

        # TODO: ConfusionMatrix does not support 3-classes now.
        metrics = {
            'train': {'loss': .0, 'f1': .0, 'recall': .0, 'precision': .0, "auroc": .0},
            'valid': {'loss': .0, 'f1': .0, 'recall': .0, 'precision': .0, "auroc": .0},
            #'test': {'loss': .0, 'f1': .0, 'recall': .0, 'precision': .0, "auroc": .0},
        }

        # Switch to training mode
        net.train()
        for batch, (x, y_true) in enumerate(train_loader):
            x, y_true = x.to(device), y_true.to(device)
            y_pred = net(x).to(torch.float32)
            y_true = y_true.to(torch.float32)

            loss = criterion(y_pred, y_true)
            loss.backward()
            optimizer.step()
            optimizer.zero_grad(set_to_none=True)

            # print("pred", y_pred)
            # print("true", y_true)
            # print(y_true.argmax(dim=1))

            y_pred = y_pred.argmax(dim=1)
            y_true = y_true.argmax(dim=1)

            print(f"{epoch}-{batch}: train_pred", y_pred.to('cpu').detach().numpy())
            #print(f"{epoch}-{batch}: pred", y_pred)
            print(f"{epoch}-{batch}: train_true", y_true.to('cpu').detach().numpy())
            # print(y_true.argmax(dim=1))

            metrics['train']['loss'] += loss.item() / len(train_loader)
            metrics['train']['f1'] += f1(y_pred, y_true).item() / len(train_loader)
            metrics['train']['recall'] += recall(y_pred, y_true).item() / len(train_loader)
            metrics['train']['precision'] += precision(y_pred, y_true).item() / len(train_loader)
            metrics['train']['auroc'] += auroc(y_pred, y_true).item() / len(train_loader)

            print("\r  Batch({:6}/{:6})[{}]: loss={:.4}, {}".format(
                batch, len(train_loader),
                ('=' * (30 * batch // len(train_loader)) + " " * 30)[:30],
                loss.item(),
                ", ".join([
                    f'{key}={metrics["train"][key]:.2}'
                    for key in ['f1', 'recall', 'precision', 'auroc']
                ])
            ), end="")
            print('\n')
        print('')

        # Save trained model
        # torch.save(net.state_dict(), workdir / f"{net.__class__.__name__}_{epoch:04}.pth")

        # Switch to training mod
        net.eval()
        with torch.no_grad():
            for x, y_true in valid_loader:
                x, y_true = x.to(device), y_true.to(device)
                y_pred = net(x).to(torch.float32)
                y_true = y_true.to(torch.float32)

                metrics['valid']['loss'] += criterion(y_pred, y_true).item() / len(valid_loader)

                y_pred_cls = y_pred.argmax(dim=1)
                y_true_cls = y_true.argmax(dim=1)

                metrics['valid']['f1'] += f1(y_pred_cls, y_true_cls).item() / len(valid_loader)
                metrics['valid']['recall'] += recall(y_pred_cls, y_true_cls).item() / len(valid_loader)
                metrics['valid']['precision'] += precision(y_pred_cls, y_true_cls).item() / len(valid_loader)
                # metrics['valid']['auroc'] += auroc(y_pred_cls, y_true_cls).item() / len(valid_loader)


            print('                    Validation: loss={:.2}, f1={:.2}, recall={:.2}, precision={:.2}, auroc={:.2}'.format(
                metrics['valid']['loss'],
                metrics['valid']['f1'],
                metrics['valid']['recall'],
                metrics['valid']['precision'],
                metrics['valid']['auroc']
            ))

        # Logging to tensorboard
        #   Ex.) logger.add_scalar('train/loss', metrics['train']['loss'], epoch)
        for ds_name, ds_vals in metrics.items():
            for key, val in ds_vals.items():
                logger.add_scalar(f"{ds_name}/{key}", val, epoch)

    return workdir


def main():
    workdir = exec_training(
        root=Path("/net/nfs3/export/dataset/morita/kobe-u/oral/MandibularCanal/"),
        annotation=Path("./_data/list-250514.csv").absolute(),
        split=Path("./_data/subject_split_fixed.csv").absolute(),
        label="hypoesthesia",
        work_root=Path("./_out/").expanduser()
    )

    print("Results written in:", workdir)


if __name__ == '__main__':
    main()
    

    